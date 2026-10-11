import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from ai_rag import RAGPipeline, build_evidence, extract_claims


class Encoder:
    def encode(self, texts, **kwargs):
        return np.array([[float('temperature' in t.lower()), float('cooling' in t.lower()), float('football' in t.lower()), float('vibration' in t.lower())] for t in texts], dtype='float32')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ocr = self.root / 'ocr.json'
        self.evidence = self.root / 'evidence.json'
        self.pages = json.loads((Path(__file__).resolve().parents[1] / 'examples/all_documents.json').read_text())
        self.write(self.pages)
        self.rag = RAGPipeline(self.ocr, self.evidence, Encoder())

    def write(self, pages):
        self.ocr.write_text(json.dumps(pages))

    def test_three_temperature_sources(self):
        response = self.rag.answer_question('What was the temperature of MX-01?')
        self.assertEqual({s['document'] for s in response['sources']}, {'Inspection_Report.pdf', 'Technician_Log.pdf', 'Machine_Manual.pdf'})
        self.assertEqual({c['value'] for c in response['verification_claims']}, {72, 91})
        self.assertEqual(response['verification_status'], 'NOT_VERIFIED')
        for source in response['sources']:
            self.assertTrue(source['source_hash'])
            self.assertIn('#page=1', source['source_reference'])
        kinds = {c['claim_kind'] for c in response['claims']}
        self.assertEqual(kinds, {'measurement', 'maximum', 'recommended_range'})

    def test_updates_replace_old_readings(self):
        self.rag.answer_question('temperature MX-01')
        self.pages[0]['text'] = self.pages[0]['text'].replace('72°C', '73°C')
        self.write(self.pages)
        result = self.rag.answer_question('temperature MX-01')
        self.assertEqual({c['value'] for c in result['verification_claims']}, {73, 91})
        self.assertEqual(len(json.loads(self.evidence.read_text())), 5)

    def test_duplicates_and_removed_documents(self):
        self.write(self.pages + self.pages)
        self.rag.sync_from_ocr()
        self.assertEqual(len(self.rag.records), 5)
        self.write([self.pages[0]])
        self.rag.sync_from_ocr()
        self.assertEqual(len(self.rag.records), 1)

    def test_no_relevant_and_empty(self):
        self.assertEqual(self.rag.answer_question('football MX-01')['answer'], 'No relevant evidence found')
        self.assertEqual(self.rag.retrieve('temperature MX-02'), [])
        self.write([])
        self.assertEqual(self.rag.answer_question('temperature MX-01')['sources'], [])

    def test_p5_and_report(self):
        received = []
        def verifier(claims):
            received.extend(claims)
            return {'verification_status': 'CONFLICTS_FOUND', 'conflicts': [{'values': [72, 91]}]}
        result = self.rag.report_payload('temperature MX-01', verifier=verifier)
        self.assertEqual(len(received), 2)
        self.assertEqual(result['verification_status'], 'CONFLICTS_FOUND')
        self.assertEqual(len(result['conflicts']), 1)
        json.dumps(result)

    def test_invalid_input_preserves_existing(self):
        self.rag.sync_from_ocr()
        before = self.evidence.read_bytes()
        with self.assertRaises(ValueError):
            self.rag.ingest([{'text': 'oops'}])
        self.assertEqual(before, self.evidence.read_bytes())
        for kwargs in [{'question': ' '}, {'question': 'x', 'top_k': 0}]:
            with self.assertRaises(ValueError):
                self.rag.retrieve(**kwargs)

    def test_context_and_encoding(self):
        self.assertEqual(build_evidence(self.pages)[3]['entities'], ['MX-01'])
        self.pages[0]['text'] = self.pages[0]['text'].replace('72°C', '72Â°C')
        self.assertEqual(extract_claims(build_evidence(self.pages))[0]['value'], 72)

    def test_restart_uses_persisted_collection(self):
        self.rag.sync_from_ocr()
        new = RAGPipeline(self.root / 'missing', self.evidence, Encoder())
        self.assertEqual(len(new.answer_question('temperature MX-01')['verification_claims']), 2)

    def test_upsert_replaces_all_document_pages(self):
        self.rag.sync_from_ocr()
        self.rag.ingest([self.pages[2]])
        self.assertEqual(len([r for r in self.rag.records if r['document'] == 'Technician_Log.pdf']), 1)
        self.rag.retrieve('temperature MX-01')
        self.assertEqual(len([r for r in self.rag.records if r['document'] == 'Technician_Log.pdf']), 1)


if __name__ == '__main__':
    unittest.main()
