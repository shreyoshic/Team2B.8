"""P4 callable retrieval module. Does not create a web server."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock

import numpy as np

ROOT = Path(__file__).resolve().parent
ENTITY = re.compile(r'\bMX[- ]?(\d+)\b', re.I)
TEMPERATURE = re.compile(r'(-?\d+(?:\.\d+)?)\s*(?:[–-]\s*(-?\d+(?:\.\d+)?)\s*)?°\s*([CF])\b', re.I)


def clean_text(text):
    # Repair mixed mojibake without damaging correctly encoded Unicode.
    for bad, good in [('â€“', '–'), ('â€”', '—'), ('Â°', '°')]:
        text = text.replace(bad, good)
    return text.strip()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = stream.name
        json.dump(value, stream, ensure_ascii=False, indent=2)
    try:
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def entities(text):
    return sorted({f'MX-{m.group(1).zfill(2)}' for m in ENTITY.finditer(text)})


def build_evidence(pages):
    if not isinstance(pages, list):
        raise ValueError('OCR output must be a JSON array of page records')
    contexts = {}
    for row in pages:
        if not isinstance(row, dict):
            raise ValueError('Each OCR record must be an object')
        for field in ('document', 'text', 'source_hash', 'extraction_method'):
            if not isinstance(row.get(field), str) or (field != 'text' and not row[field].strip()):
                raise ValueError(f'OCR record requires {field}')
        if isinstance(row.get('page'), bool) or not isinstance(row.get('page'), int) or row['page'] < 1:
            raise ValueError('page must be a positive integer')
        contexts.setdefault(row['document'], set()).update(entities(row['text']))
    records, seen = [], set()
    for row in pages:
        text = clean_text(row['text'])
        if not text:
            continue
        explicit = entities(text)
        inherited = sorted(contexts[row['document']])
        entity_ids = explicit or (inherited if len(inherited) == 1 else [])
        # Keep page-local chunks and line ranges, including unassigned documents.
        lines = text.splitlines()
        start = 0
        while start < len(lines):
            end, size = start, 0
            while end < len(lines) and (size < 1000 or end == start):
                size += len(lines[end]) + 1
                end += 1
            passage = '\n'.join(lines[start:end])
            identity = hashlib.sha256(json.dumps([row['document'], row['page'], start, row['source_hash'], passage]).encode()).hexdigest()
            if identity not in seen:
                records.append({
                    'chunk_id': identity, 'evidence_id': entity_ids[0] if len(entity_ids) == 1 else None,
                    'entities': entity_ids, 'document': row['document'], 'page': row['page'],
                    'text': passage, 'source_hash': row['source_hash'],
                    'source_reference': f"{row['document']}#page={row['page']}",
                    'source_type': 'document', 'location': f"page {row['page']}, lines {start + 1}–{end}",
                    'extraction_method': row['extraction_method'],
                    'metadata': {'provenance': 'ocr_output', 'verification_status': 'NOT_VERIFIED'},
                })
                seen.add(identity)
            start = end
    return records


def extract_claims(evidence):
    claims = []
    for row in evidence:
        for line in row['text'].splitlines():
            if 'temperature' not in line.lower():
                continue
            ids = entities(line) or row['entities']
            if len(ids) != 1:
                continue  # Do not guess which machine a mixed-source claim describes.
            match = TEMPERATURE.search(line)
            if not match:
                continue
            a, b, unit = match.groups()
            lower = line.lower()
            kind = 'recommended_range' if b else 'maximum' if 'maximum' in lower else 'recommended' if 'recommended' in lower else 'measurement'
            claim = {'entity': ids[0], 'claim': 'temperature', 'value': float(a),
                     'unit': '°' + unit.upper(), 'claim_kind': kind,
                     'source': row['document'], 'page': row['page'],
                     'source_reference': row['source_reference'], 'source_hash': row['source_hash'],
                     'evidence_text': line, 'chunk_id': row['chunk_id']}
            if b:
                claim['value'] = [float(a), float(b)]
            date = re.search(r'(?:Inspection Date|Date|Timestamp):\s*([^\n]+)', row['text'], re.I)
            if date:
                claim['timestamp_text'] = date.group(1).strip()
            claims.append(claim)
    return claims


class RAGPipeline:
    """Single-process service owned by P2. Pass encoder for offline tests."""
    def __init__(self, ocr_path=None, evidence_path=None, encoder=None, model_name='sentence-transformers/all-MiniLM-L6-v2'):
        self.ocr_path = Path(ocr_path) if ocr_path else ROOT.parent / 'ocr/output/all_documents.json'
        self.evidence_path = Path(evidence_path) if evidence_path else ROOT / 'data/mx01_evidence.json'
        self.model_name, self.encoder = model_name, encoder
        self.lock = RLock()
        self.records, self.vectors = [], None
        self.fingerprint = None
        if self.evidence_path.exists():
            self.records = json.loads(self.evidence_path.read_text(encoding='utf-8'))

    def _model(self):
        if self.encoder is None:
            from sentence_transformers import SentenceTransformer
            self.encoder = SentenceTransformer(self.model_name)
        return self.encoder

    def _encode(self, texts):
        vectors = np.ascontiguousarray(self._model().encode(texts, normalize_embeddings=True, convert_to_numpy=True), dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(texts) or not np.isfinite(vectors).all():
            raise ValueError('Invalid embeddings')
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)

    def ingest(self, pages, replace_all=False):
        """After upload: upsert all pages of affected documents, or replace snapshot."""
        with self.lock:
            new = build_evidence(pages)
            affected = {r['document'] for r in pages}
            combined = new if replace_all else [r for r in self.records if r['document'] not in affected] + new
            # Persist only after validation succeeds. Empty replacement clears stale evidence.
            atomic_json(self.evidence_path, combined)
            self.records, self.vectors = combined, None
            if self.ocr_path.exists():
                self.fingerprint = hashlib.sha256(self.ocr_path.read_bytes()).hexdigest()
            return {'status': 'INGESTED', 'evidence_count': len(combined), 'documents_updated': sorted(affected)}

    def sync_from_ocr(self):
        with self.lock:
            if not self.ocr_path.exists():
                return {'status': 'OCR_OUTPUT_MISSING', 'evidence_count': len(self.records)}
            content = self.ocr_path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != self.fingerprint:
                result = self.ingest(json.loads(content.decode('utf-8')), replace_all=True)
                self.fingerprint = digest
                return result
            return {'status': 'UNCHANGED', 'evidence_count': len(self.records)}

    def retrieve(self, question, entity=None, top_k=8, min_score=0.35):
        if not isinstance(question, str) or not question.strip():
            raise ValueError('question must not be blank')
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
            raise ValueError('top_k must be between 1 and 50')
        if not -1 <= min_score <= 1:
            raise ValueError('min_score must be between -1 and 1')
        with self.lock:
            self.sync_from_ocr()
            ids = entities(question)
            entity = entity.upper() if entity else (ids[0] if len(ids) == 1 else None)
            positions = [i for i, row in enumerate(self.records) if entity is None or entity in row['entities']]
            if not positions:
                return []
            import faiss
            if self.vectors is None:
                self.vectors = self._encode([r['text'] for r in self.records])
            index = faiss.IndexFlatIP(self.vectors.shape[1])
            index.add(np.ascontiguousarray(self.vectors[positions]))
            scores, indices = index.search(self._encode([question]), min(top_k, len(positions)))
            return [{**self.records[positions[int(i)]], 'score': round(float(score), 4)}
                    for score, i in zip(scores[0], indices[0]) if i >= 0 and score >= min_score]

    def answer_question(self, question, verifier=None, **kwargs):
        with self.lock:
            hits = self.retrieve(question, **kwargs)
            claims = extract_claims(hits)
            measurements = [c for c in claims if c['claim_kind'] == 'measurement']
            # Only comparable measurements go to P5; limits remain contextual claims.
            verification = verifier(measurements) if verifier and measurements else None
            if verification is not None and not isinstance(verification, dict):
                raise ValueError('P5 verifier must return a JSON-compatible dict')
            if not hits:
                answer = 'No relevant evidence found'
            else:
                answer = '\n\n'.join(f"[{r['source_reference']}]\n{r['text']}" for r in hits)
            return {'question': question, 'answer': answer, 'sources': hits,
                    'claims': claims, 'verification_claims': measurements,
                    'retrieval_status': 'EVIDENCE_FOUND' if hits else 'NO_RELEVANT_EVIDENCE',
                    'verification_status': verification.get('verification_status', 'NOT_VERIFIED') if verification else 'NOT_VERIFIED',
                    'conflicts': verification.get('conflicts', []) if verification else [],
                    'verification': verification}

    def report_payload(self, question, verifier=None, **kwargs):
        """Structured evidence/claims payload for P2's report renderer."""
        return self.answer_question(question, verifier=verifier, **kwargs)
