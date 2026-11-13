"""Read traceable PDF/JSONL units; keep paragraph boundaries."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from .models import DocumentPage


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "").replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    from pypdf import PdfReader
    pages = []
    for number, page in enumerate(PdfReader(path).pages, 1):
        try:
            text = normalize_text(page.extract_text(extraction_mode="layout") or "")
            metadata = {"read_status": "ok" if text else "empty"}
        except Exception as exc:
            text, metadata = "", {"read_status": "error", "error_type": type(exc).__name__}
        pages.append(DocumentPage(document_id, source, number, text, metadata))
    return pages


def load_corpus(manifest_path: Path) -> tuple[list[DocumentPage], list[dict]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages, log, seen = [], [], set()
    for entry in manifest["sources"]:
        for field in ("source_id", "title", "path", "source_url", "license_or_permission", "accessed_at", "page_ids", "sha256"):
            if not entry.get(field):
                raise ValueError(f"Manifest source missing {field}")
        path = (manifest_path.parent / entry["path"]).resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source checksum changed: {entry['source_id']}; rebuild manifest/benchmark")
        if entry.get("format") == "pdf":
            loaded = load_pdf(path, entry["source_id"], entry["source_url"])
        elif entry.get("format") == "jsonl":
            loaded = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    loaded.append(DocumentPage(entry["source_id"], entry["source_url"], row["page"], normalize_text(row["text"]), row.get("metadata", {})))
        else:
            raise ValueError("Supported source formats: pdf, jsonl")
        for page in loaded:
            key = (page.document_id, page.page)
            if key in seen:
                raise ValueError(f"Duplicate source/page: {key}")
            seen.add(key)
            page.metadata = {**entry.get("metadata", {}), **page.metadata}
            counted = page.page in entry["page_ids"]
            status = page.metadata.get("read_status", "ok" if page.text else "empty")
            log.append({"document_id": page.document_id, "page": page.page, "status": status,
                        "characters": len(page.text), "counted": counted})
            if counted:
                if not page.text:
                    raise ValueError(f"Counted page is unreadable/empty: {key}")
                if entry.get("format") == "jsonl" and entry.get("unit_type") != "pdf_page" and len(page.text) < 1500:
                    raise ValueError(f"Text unit below 1500 normalized characters: {key}")
                if not page.metadata.get("category"):
                    raise ValueError(f"Missing filter metadata category: {key}")
                pages.append(page)
        if set(entry["page_ids"]) - {p.page for p in loaded}:
            raise ValueError(f"Manifest refers to absent pages: {entry['source_id']}")
    if len(pages) < 30:
        raise ValueError(f"Corpus requires >=30 content units; found {len(pages)}")
    if len({p.metadata["category"] for p in pages}) < 2:
        raise ValueError("Corpus requires at least two verified categories for filtering")
    return pages, log
