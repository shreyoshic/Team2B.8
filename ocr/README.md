# Multi-Source Document Extraction

A document-processing module for the hackathon problem
"Multi Source Ingestion into a Single Verifiable Document".

It extracts text from local files and public URLs into a common
record structure for downstream processing and verification.

## Supported File Types

- PDF
- TXT and LOG
- DOCX
- PPTX
- XLSX
- CSV
- JPG, JPEG and PNG
- Public HTML webpages
- Direct PDF URLs

## Features

- PDF text extraction using PyMuPDF
- OCR for scanned PDFs and images using Tesseract
- Extraction from Word, PowerPoint, Excel and CSV files
- Public webpage text extraction using BeautifulSoup
- Direct PDF URL retrieval and text extraction
- Source URL, title and retrieval timestamp for URL records
- SHA-256 source hash
- Source references for pages where available
- Common JSON record structure
- Extraction method recorded as text, OCR or HTML
- OCR confidence estimate where available
- Per-file error handling

## Output

Local file extraction saves records to
`output/all_documents.json`.

Each record contains fields such as `document`, `page`, `text`,
`source_hash` and `extraction_method`. URL records also include
`source_url`, `title` and `retrieved_at`.

## Setup

Install Python dependencies:

`pip install -r requirements.txt`

Tesseract OCR must be installed separately for OCR functionality.

## Usage: Local Files

1. Place supported files inside `documents/`.
2. Run `python3 extract_text.py`.
3. Find the results in `output/all_documents.json`.

## Usage: Public URLs

Run the URL ingestion module:

`python3 -m ingestion.url_ingestion`

When prompted, enter a public HTML webpage URL or a direct PDF URL.
The module prints extracted record details and a text preview.

The `ingest_url(url)` function can also be imported and called by
other Python modules. It returns a list of source records.

Unsupported formats and inaccessible URLs return clear errors.
