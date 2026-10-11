# P4 — MX-01 retrieval and claim extraction

Copy this `ai_rag` folder into your TechSmiths repository. It is a Python module; it creates no FastAPI server and does not modify the frontend, OCR, or verification modules. Replace the earlier ai_rag add-on folder after keeping any needed backup; its old backend/app.py is no longer used.

## Install and test

From the repository root:

```bash
python -m pip install -r ai_rag/requirements.txt
python -m unittest discover -s ai_rag/tests -v
python -m ai_rag --ocr ocr/output/all_documents.json --ingest-only
python -m ai_rag --question "What was the temperature of MX-01?"
```

Production uses Sentence Transformers `all-MiniLM-L6-v2`, normalized embeddings, and FAISS cosine ranking. First use downloads the model; provision/cache it before running offline. Dependency or model errors propagate to P2 and must be shown as service errors, never as “No relevant evidence found.” The default cosine threshold is 0.35 and should be calibrated on your documents.

## P2 connection (existing central backend)

Construct one shared service in P2, using absolute paths:

```python
from pathlib import Path
from ai_rag import RAGPipeline

PROJECT = Path(__file__).resolve().parents[1]  # backend/main.py
rag = RAGPipeline(
    ocr_path=PROJECT / 'ocr/output/all_documents.json',
    evidence_path=PROJECT / 'ai_rag/data/mx01_evidence.json',
)
```

In P2's `/upload`, AFTER P3 has successfully written its complete combined OCR output:

```python
rag.sync_from_ocr()
```

Alternatively, if P3 returns pages directly rather than a complete snapshot:

```python
rag.ingest(extracted_pages)
```

`ingest()` replaces all previous pages of each affected document name; send ALL pages of every updated document. Duplicate pages are removed. `sync_from_ocr()` treats the combined OCR file as the authoritative complete collection, including deletions. Changed file contents refresh retrieval automatically before each question. Write OCR snapshots atomically to avoid partial JSON reads. Use one ingestion path consistently; a subsequent changed complete OCR snapshot replaces the collection.

In P2's `/question`, accept JSON `{"question": "What was the temperature of MX-01?"}` and call:

```python
result = rag.answer_question(body.question)
```

For P5 integration, wrap P5's existing entry point with a function accepting a list of claims and returning its JSON dict:

```python
result = rag.answer_question(body.question, verifier=verify_claims)
```

`verify_claims` above is P2's adapter to P5, not a function provided by this module. Only measured temperature claims go to that adapter. Recommended ranges and maxima are available separately in `claims`. Missing P5 returns `NOT_VERIFIED`; P4 never fabricates a verification result.

Use the same service for report generation:

```python
report_data = rag.report_payload(question, verifier=verify_claims)
# Pass report_data to P2's existing PDF/Word/report renderer.
```

For GET `/report`, P2 must retain the selected question/report or accept a question query parameter. This package supplies report data, not a PDF/Word renderer. For async FastAPI handlers, run these blocking calls in FastAPI's thread pool (or use synchronous `def` handlers).

## Output

`answer` contains the supporting passages with citations. It is extractive, not an LLM-generated conclusion. `sources` includes text, document, page, line range, source reference, source hash, extraction method, and cosine score. `claims` contains measurements and limits; `verification_claims` contains measured readings for P5. Report output uses the same schema.

No qualifying hits returns:

```json
{
  "answer": "No relevant evidence found",
  "sources": [],
  "claims": [],
  "verification_claims": [],
  "retrieval_status": "NO_RELEVANT_EVIDENCE",
  "verification_status": "NOT_VERIFIED",
  "conflicts": [],
  "verification": null
}
```

The full response also includes `question`. Entity filtering occurs before ranking. An MX-01 question cannot retrieve MX-02-only records. Continuation pages inherit a machine only when the document has exactly one machine ID; ambiguous claims are omitted rather than guessed. Claim extraction currently supports explicitly labeled numeric temperatures in °C and °F, including ranges. Other claim types require extending the parser.

## Supplied evidence

`examples/all_documents.json` is the supplied OCR output, copied unchanged. `data/mx01_evidence.json` contains its actual passages: inspection 72°C, technician 91°C, manual range 60–75°C and maximum 80°C. The hashes are retained as supplied by P3; P4 has not independently recomputed hashes against the original PDFs. OCR provenance does not mean factual verification. These records are marked `NOT_VERIFIED` until P5 runs.

The inspection includes a date while the log does not. P5 should account for observation times; differing readings may be observations at different times. This module retains date text when present and never invents dates.

## Validation and deployment limits

The unit suite uses real FAISS with deterministic test embeddings to check ingestion, replacement, deduplication, source references, entity filtering, no-hit behavior, extraction, restart, and P5/report handoff. A production-model smoke test also passed: the temperature question returned Inspection_Report.pdf (0.6567), Machine_Manual.pdf (0.5568), and Technician_Log.pdf (0.4990), with measured claims 72°C and 91°C. An unrelated football question returned no evidence. The complete response is included in examples/temperature_response.json. These checks do not establish quality for all questions. This service caches embeddings in memory and persists evidence JSON. It uses a process lock: run one backend worker, or supply a shared coordinated storage layer before scaling to multiple workers. It supports one project-wide collection; production multi-user isolation is P2's responsibility.

The central backend supplied earlier has placeholder routes. P2 must insert the calls above; no browser end-to-end test can pass until those routes and P5 are connected.
