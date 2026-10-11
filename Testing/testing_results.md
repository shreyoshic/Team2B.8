# Person 6 - Testing Results

## Project

Multi Source Ingestion into a Single Verifiable Document

## Role

Testing and Integration

## 1\. Test Results

|Test Case|Expected Result|Actual Result|Status|
|-|-|-|-|
|PDF Text Extraction|Extract text from PDF documents|Text extracted from the project PDFs|PASS|
|OCR Image Extraction|Extract text from scanned images|MX-01 image text extracted successfully|PASS|
|Combined Output|Combine extracted document results|Combined JSON output generated|PASS|
|Entity Matching|Identify equivalent entity names|MX-01, MX01, and Machine 01 matched correctly|PASS|
|Different Entity Check|Distinguish different entities|MX-01 and MX-02 were not matched|PASS|
|Claim Matching|Identify equivalent claims|Temperature claims matched; pressure was distinguished|PASS|
|Value Comparison|Compare claim values|Identical values matched; different values produced a conflict|PASS|
|Conflict Detection|Identify conflicting claims|72°C and 91°C produced a conflict|PASS|
|Source References|Preserve document, page, and source hash|Source information appeared in verification output|PASS|
|Existing Team Tests|Run existing test suite|All P5 tests passed|PASS|
|Retrieval Tests|Verify retrieval behavior|Three tests ran successfully|PASS|
|Real MX-01 Retrieval|Retrieve actual verified MX-01 evidence|Evidence file is empty; real-source retrieval not verified|BLOCKED|

## 2\. Issues Identified

### Issue 1: OCR did not initially support PNG images

* Original behavior: PNG images were not included in the supported file types.
* Action taken: Added PNG and JPEG image handling using Tesseract OCR.
* Result: OCR test passed.

### Issue 2: Retrieval module was missing evidence.py

* Original behavior: Retrieval tests failed with ModuleNotFoundError for backend.evidence.
* Action taken: Restored evidence.py from the supplied TechSmiths\_MX01\_RAG.zip package.
* Result: All three retrieval tests passed.

### Issue 3: MX-01 retrieval evidence is empty

* Observation: ai\_rag/data/mx01\_evidence.json contains an empty JSON array.
* Impact: Retrieval with actual verified MX-01 evidence cannot yet be validated.
* Recommended action: Populate the file with verified evidence chunks from the document ingestion pipeline.

### Issue 4: Temperature conflict requires contextual verification

* Observation: The sample verification test identifies 72°C and 91°C as conflicting values.
* Note: Confirm that both values refer to the same operating condition and measurement context before deciding that the underlying documents contradict each other.

## 3\. Testing Limitations

* Retrieval tests use deterministic test embeddings.
* Actual retrieval quality against real MX-01 evidence has not been verified.
* The complete frontend-to-backend end-to-end workflow has not yet been confirmed.
* Successful module tests do not establish that all modules are fully integrated.

## 4\. Overall Status

Core extraction, OCR, entity matching, conflict detection, verification, and retrieval unit tests passed.
Further integration testing is required, especially with real MX-01 evidence.

Prepared by: Person 6 - Testing and Integration





## Additional Testing Results — 10 October 2026



### 1. Evidence Loading

Result: PASS

- Four evidence records loaded successfully.

- Source references and page locations were preserved.

- The unrelated page 3 record containing only "Yes" was excluded pending clarification.



### 2. AI/RAG Health Check

- Result: PASS

- Application health: OK

- Verified evidence records loaded: 4

- Embedding model: sentence-transformers/all-MiniLM-L6-v2

- Application status: ready



### 3. AI/RAG Retrieval

- Result: PASS

- Query tested: "What is the operating temperature of MX-01?"

- Retrieval status: retrieved

- Three source references returned:

&#x20; - Inspection\_Report.pdf#page=1

&#x20; - Machine\_Manual.pdf#page=1

&#x20; - Technician\_Log.pdf#page=1

- Both temperature observations, 72°C and 91°C, were returned.

- Issue identified: temperature symbols display incorrectly in some API output.



### 4. Entity Matching and Conflict Detection

- Result: PASS for the tested cases.

- MX-01 matched MX01 and Machine 01.

- MX-01 did not match MX-02.

- Identical values returned MATCH.

- 72°C versus 91°C returned CONFLICT.

- The sample verification workflow reported CONFLICTS\_FOUND with one conflict.



### 5. Issues and Limitations

- Character encoding needs investigation.

- The verification sample uses demonstration source names and hashes rather than the actual PDF source references.

- The verification logic has been tested, but integration of the verifier with real extracted evidence is not yet confirmed.

- Full frontend-to-backend end-to-end testing remains pending.

### Successfully Tested Modules

1. **PDF Upload & Text Extraction:** Successfully uploaded `Inspection_Report.pdf` and extracted 1 record.
2. **Question Answering & Retrieval:** Retrieved MX-01 inspection information with a source reference (`Inspection_Report.pdf`, page 1).
3. **URL Ingestion:** Successfully ingested `https://example.com`, created a text file, and indexed 1 record.
4. **Report Generation:** Successfully generated a report containing 2 documents and the detected temperature of 72°C.
5. **Conflict Resolution:** Successfully processed a sample conflict-resolution request and returned `RESOLVED_BY_REVIEWER`.


