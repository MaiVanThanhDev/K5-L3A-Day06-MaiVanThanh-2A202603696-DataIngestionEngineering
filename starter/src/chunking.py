"""Deterministic chunk IDs and normalized character offsets per source unit."""
import hashlib
import re
from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, start: int, end: int, method: str) -> Chunk:
    while start < end and page.text[start].isspace():
        start += 1
    while end > start and page.text[end - 1].isspace():
        end -= 1
    text = page.text[start:end]
    identity = f"{page.document_id}:{page.page}:{method}:{start}:{end}:{text}"
    chunk_id = hashlib.sha256(identity.encode()).hexdigest()
    return Chunk(chunk_id, page.document_id, page.source, page.page, text,
                 {**page.metadata, "char_start": start, "char_end": end, "chunking": method})


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Require size > 0 and 0 <= overlap < size")
    chunks = []
    for start in range(0, len(page.text), size - overlap):
        end = min(start + size, len(page.text))
        chunk = _chunk(page, start, end, "fixed")
        if chunk.text:
            chunks.append(chunk)
        if end == len(page.text):
            break
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    spans = []
    for match in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", page.text):
        start, end = match.span()
        while end - start > max_size:
            cut = page.text.rfind(" ", start + max_size // 2, start + max_size + 1)
            if cut <= start:
                cut = start + max_size
            spans.append((start, cut))
            start = cut
            while start < end and page.text[start].isspace():
                start += 1
        if start < end:
            spans.append((start, end))
    groups = []
    for start, end in spans:
        if groups and end - groups[-1][0] <= max_size:
            groups[-1] = (groups[-1][0], end)
        else:
            groups.append((start, end))
    return [_chunk(page, start, end, "paragraph") for start, end in groups]
