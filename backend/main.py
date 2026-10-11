
import hashlib
import ipaddress
import socket
import urllib.request
import urllib.error
import json
import re

from urllib.parse import urlparse
from html.parser import HTMLParser
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from pathlib import Path

from ocr.extract_text import extract_file, SUPPORTED_EXTENSIONS


app = FastAPI(title="VeriTrace Backend")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "ocr" / "output"
INDEX_FILE = OUTPUT_DIR / "all_documents.json"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# -------------------- REQUEST MODELS --------------------

class QuestionRequest(BaseModel):
    question: str


class URLIngestRequest(BaseModel):
    url: str


class ConflictResolutionRequest(BaseModel):
    conflict_id: str
    selected_value: str
    rationale: str
    reviewed_by: str = "human_reviewer"


# -------------------- DOCUMENT INDEX --------------------

def load_index():
    if not INDEX_FILE.exists():
        return []

    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return []


def save_index(records):
    with open(INDEX_FILE, "w", encoding="utf-8") as file:
        json.dump(records, file, indent=4, ensure_ascii=False)


def index_file(file_path):
    # Extract before replacing old records.
    new_records = extract_file(str(file_path))

    records = load_index()
    records = [
        record for record in records
        if record.get("document") != file_path.name
    ]
    records.extend(new_records)
    save_index(records)

    return new_records


def index_existing_uploads():
    for file_path in sorted(UPLOAD_DIR.iterdir()):
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            index_file(file_path)
            print(f"Indexed: {file_path.name}")
        except Exception as error:
            print(f"Could not index {file_path.name}: {error}")


# -------------------- TEMPERATURE VERIFICATION --------------------

def extract_temperature_records(records):
    results = []
    pattern = r"(-?\d+(?:\.\d+)?)\s*°\s*C\b"

    for record in records:
        text = record.get("text", "")

        for match in re.finditer(pattern, text, re.IGNORECASE):
            results.append({
                "temperature_celsius": float(match.group(1)),
                "document": record.get("document"),
                "page": record.get("page")
            })

    return results


def get_verification_status(temperature_records):
    values = {
        item["temperature_celsius"]
        for item in temperature_records
    }

    return "REVIEW_REQUIRED" if len(values) > 1 else "PENDING"


# -------------------- URL INGESTION --------------------

class PageTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_tags = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_tags.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in self.skip_tags:
            self.skip_tags.remove(tag)

    def handle_data(self, data):
        if not self.skip_tags and data.strip():
            self.parts.append(data.strip())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not automatically follow redirects to another destination.
        return None


def fetch_public_page(url):
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid URL or port.")

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query == ""
        and not parsed.netloc
    ):
        raise ValueError("Provide a valid public HTTP or HTTPS URL.")

    expected_port = 443 if parsed.scheme == "https" else 80

    if port is not None and port != expected_port:
        raise ValueError("Only standard HTTP and HTTPS ports are allowed.")

    hostname = parsed.hostname

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                hostname, expected_port, type=socket.SOCK_STREAM
            )
        }
    except socket.gaierror:
        raise ValueError("Could not resolve the website hostname.")

    if not addresses:
        raise ValueError("No public IP address was found.")

    for address in addresses:
        ip = ipaddress.ip_address(address)

        if not ip.is_global:
            raise ValueError("Private or non-public destinations are blocked.")

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "VeriTrace/1.0"}
    )

    opener = urllib.request.build_opener(NoRedirect)

    try:
        with opener.open(request, timeout=8) as response:
            if response.status != 200:
                raise ValueError("Website did not return HTTP 200.")

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if "text/html" not in content_type:
                raise ValueError("URL must return an HTML webpage.")

            content = response.read(2_000_001)

            if len(content) > 2_000_000:
                raise ValueError("Webpage exceeds the 2 MB limit.")

            charset = response.headers.get_content_charset() or "utf-8"
            html = content.decode(charset, errors="replace")

    except urllib.error.HTTPError as error:
        raise ValueError(
            f"Website returned HTTP {error.code}; redirects are not followed."
        )

    parser = PageTextParser()
    parser.feed(html)

    return "\n".join(parser.parts)


@app.post("/ingest-url")
def ingest_url(request: URLIngestRequest):
    try:
        text = fetch_public_page(request.url)

        if not text.strip():
            raise ValueError("No readable webpage text was found.")

        url_hash = hashlib.sha256(
            request.url.encode("utf-8")
        ).hexdigest()[:16]

        filename = f"url_{url_hash}.txt"
        file_path = UPLOAD_DIR / filename

        file_path.write_text(text, encoding="utf-8")

        records = index_file(file_path)

        return {
            "status": "SUCCESS",
            "source_url": request.url,
            "document": filename,
            "records_extracted": len(records),
            "message": "Webpage extracted and indexed successfully."
        }

    except (ValueError, urllib.error.URLError, TimeoutError, OSError) as error:
        raise HTTPException(status_code=400, detail=str(error))


# -------------------- STARTUP --------------------

@app.on_event("startup")
def startup():
    index_existing_uploads()


# -------------------- HOME --------------------

@app.get("/")
def home():
    return {"message": "VeriTrace Backend is running!"}


# -------------------- 1. UPLOAD DOCUMENT --------------------

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    filename = Path(file.filename or "uploaded_file").name

    if not filename or filename == ".":
        raise HTTPException(status_code=400, detail="Invalid filename")

    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format"
        )

    file_path = UPLOAD_DIR / filename

    try:
        content = await file.read(10_000_001)

        if len(content) > 10_000_000:
            raise HTTPException(
                status_code=413,
                detail="File exceeds the 10 MB limit."
            )

        file_path.write_bytes(content)

    finally:
        await file.close()

    try:
        records = index_file(file_path)

        return {
            "message": "File uploaded and extracted successfully",
            "file": filename,
            "records_extracted": len(records),
            "extraction_status": "SUCCESS",
            "ocr_confidence": [
                {
                    "page": record.get("page"),
                    "confidence": record.get("ocr_confidence"),
                    "extraction_method": record.get("extraction_method")
                }
                for record in records
            ]
        }

    except Exception as error:
        return {
            "message": "File uploaded, but text extraction failed",
            "file": filename,
            "extraction_status": "FAILED",
            "reason": str(error)
        }


# -------------------- 2. ASK QUESTIONS --------------------

@app.post("/question")
def question(request: QuestionRequest):
    records = load_index()
    question_text = request.question.lower()

    stop_words = {
        "what", "is", "the", "a", "an", "of", "in", "to",
        "for", "and", "does", "do", "tell", "me", "about",
        "please", "can", "you", "was", "were", "recorded",
        "found", "show", "give", "find", "with", "on", "at",
        "it", "this", "that"
    }

    question_words = (
        set(re.findall(r"[a-z0-9]+", question_text)) - stop_words
    )

    matches = []

    for record in records:
        text_lower = record.get("text", "").lower()

        score = sum(
            1 for word in question_words
            if len(word) > 1 and word in text_lower
        )

        if score > 0:
            matches.append((score, record))

    matches.sort(key=lambda item: item[0], reverse=True)

    temperature_words = {
        "temperature", "temperatures", "temp",
        "celsius", "degree", "degrees"
    }

    asks_temperature = bool(
        set(re.findall(r"[a-z]+", question_text))
        & temperature_words
    )

    temperature_records = (
        extract_temperature_records(records)
        if asks_temperature else []
    )

    if matches:
        best = matches[0][1]
        answer = best.get("text", "")[:1000]
        sources = [
            f'{best.get("document")}, page {best.get("page")}'
        ]
    else:
        answer = "No matching information found in extracted documents."
        sources = []

    return {
        "question": request.question,
        "answer": answer,
        "sources": sources,
        "conflicts": temperature_records,
        "verification_status": get_verification_status(
            temperature_records
        )
    }


# -------------------- 3. VERIFICATION --------------------

@app.get("/verification")
def verification():
    records = load_index()
    temperatures = extract_temperature_records(records)

    unique_values = sorted({
        item["temperature_celsius"] for item in temperatures
    })

    status = get_verification_status(temperatures)

    if status == "REVIEW_REQUIRED":
        message = (
            "Different temperature values were found. "
            "Review their context before deciding whether they conflict."
        )
    elif temperatures:
        message = (
            "Temperature values were found, but a conflict "
            "has not been confirmed."
        )
    else:
        message = "No readable Celsius temperature values were detected."

    return {
        "status": status,
        "message": message,
        "temperature_values_found": len(temperatures),
        "unique_temperature_values": unique_values,
        "findings": temperatures
    }


# -------------------- 4. REPORT --------------------

@app.get("/report")
def report():
    records = load_index()
    temperatures = extract_temperature_records(records)

    documents = {}

    for record in records:
        filename = record.get("document", "unknown")

        if filename not in documents:
            documents[filename] = set()

        documents[filename].add(str(record.get("page", "")))

    status = get_verification_status(temperatures)

    return {
        "report_status": status,
        "documents_count": len(documents),
        "documents": [
            {
                "filename": filename,
                "pages": len(page_numbers)
            }
            for filename, page_numbers in documents.items()
        ],
        "temperatures_found": temperatures,
        "message": (
            "Different temperature values detected; review their context."
            if status == "REVIEW_REQUIRED"
            else "No differing temperature values detected, "
                 "or more information is needed."
        )
    }


# -------------------- 5. RESOLVE CONFLICT --------------------

@app.post("/resolve-conflict")
def resolve_conflict(request: ConflictResolutionRequest):
    if not request.conflict_id.strip():
        raise HTTPException(
            status_code=400,
            detail="conflict_id is required"
        )

    if not request.selected_value.strip():
        raise HTTPException(
            status_code=400,
            detail="selected_value is required"
        )

    if not request.rationale.strip():
        raise HTTPException(
            status_code=400,
            detail="A rationale is required"
        )

    return {
        "status": "RESOLVED_BY_REVIEWER",
        "conflict_id": request.conflict_id,
        "selected_value": request.selected_value,
        "rationale": request.rationale,
        "reviewed_by": request.reviewed_by,
        "automatically_verified": False
    }
