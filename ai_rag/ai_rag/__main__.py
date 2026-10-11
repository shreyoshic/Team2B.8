import argparse
import json
from .pipeline import RAGPipeline

parser = argparse.ArgumentParser(description='P4 evidence ingestion or question smoke test; no web server')
parser.add_argument('--ocr', help='Complete OCR snapshot path')
parser.add_argument('--ingest-only', action='store_true')
parser.add_argument('--question', default='What was the temperature of MX-01?')
args = parser.parse_args()
rag = RAGPipeline(ocr_path=args.ocr)
result = rag.sync_from_ocr() if args.ingest_only else rag.answer_question(args.question)
print(json.dumps(result, indent=2, ensure_ascii=False))
