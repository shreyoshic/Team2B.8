import hashlib
import os
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

import requests
import pymupdf
from bs4 import BeautifulSoup
from ocr.extract_text import extract_pdf, make_record


TIMEOUT = 20
MAX_DOWNLOAD_SIZE = 15 * 1024 * 1024  # 15 MB


def ingest_url(url):
    """Extract text and source information from a public HTML page or PDF URL."""

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Please provide a valid HTTP or HTTPS URL.")

    if parsed.username or parsed.password:
        raise ValueError("URLs containing embedded credentials are unsupported.")

    retrieved_at = datetime.now(timezone.utc).isoformat()

    try:
        with requests.get(
            url,
            timeout=TIMEOUT,
            stream=True,
            headers={"User-Agent": "VeriTrace-Document-Ingestion/1.0"},
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            ).split(";")[0].strip().lower()

            chunks = []
            total_size = 0

            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue

                total_size += len(chunk)

                if total_size > MAX_DOWNLOAD_SIZE:
                    raise ValueError("URL content exceeds the 15 MB limit.")

                chunks.append(chunk)

            content = b"".join(chunks)
            final_url = response.url

    except requests.RequestException as error:
        raise ValueError(
            f"Could not retrieve URL: {error}"
        ) from error

    final_parsed = urlparse(final_url)

    if final_parsed.scheme not in {"http", "https"} or not final_parsed.hostname:
        raise ValueError("The URL redirected to an unsupported address.")

    source_hash = hashlib.sha256(content).hexdigest()

    is_pdf = (
        content_type == "application/pdf"
        or content.startswith(b"%PDF-")
    )

    if is_pdf:
        filename = os.path.basename(unquote(final_parsed.path)) or "document.pdf"

        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        with tempfile.NamedTemporaryFile(suffix=".pdf") as temp:
            temp.write(content)
            temp.flush()

            try:
                records = extract_pdf(temp.name)

                with pymupdf.open(temp.name) as pdf:
                    title = (pdf.metadata or {}).get("title") or filename

            except Exception as error:
                raise ValueError(
                    f"Could not extract PDF content: {error}"
                ) from error

        for record in records:
            record["document"] = filename
            record["source_hash"] = source_hash
            record["source_url"] = final_url
            record["title"] = title
            record["retrieved_at"] = retrieved_at

        return records

    if content_type in {"text/html", "application/xhtml+xml"} or (
        not content_type
        and content.lstrip().startswith(b"<")
    ):
        try:
            soup = BeautifulSoup(content, "html.parser")
        except Exception as error:
            raise ValueError(
                f"Could not parse HTML content: {error}"
            ) from error

        title = soup.title.get_text(" ", strip=True) if soup.title else ""

        for element in soup(
            ["script", "style", "noscript", "template"]
        ):
            element.decompose()

        text = soup.get_text(separator="\n", strip=True)

        if not text:
            raise ValueError("The webpage contains no extractable text.")

        record = make_record(
            final_parsed.hostname,
            "webpage",
            text,
            source_hash,
            method="html",
        )

        record["source_url"] = final_url
        record["title"] = title or final_parsed.hostname
        record["retrieved_at"] = retrieved_at

        return [record]

    raise ValueError(
        f"Unsupported content type: {content_type or 'unknown'}"
    )


if __name__ == "__main__":
    url = input("Enter a public webpage or direct PDF URL: ").strip()

    try:
        records = ingest_url(url)

        print(f"Successfully extracted {len(records)} record(s).")

        for record in records:
            print(f"\nTitle: {record['title']}")
            print(f"Source: {record['source_url']}")
            print(f"Retrieved at: {record['retrieved_at']}")
            print(f"Reference: {record['page']}")
            print(f"Method: {record['extraction_method']}")
            print(f"Text preview: {record['text'][:500]}")

    except ValueError as error:
        print(f"Ingestion failed: {error}")
