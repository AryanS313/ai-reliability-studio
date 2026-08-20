from __future__ import annotations

from typing import Any

from src.utils import source_title
from src.versioning import text_hash


def chunk_text(
    text: str,
    filename: str,
    chunk_size_words: int = 650,
    overlap_words: int = 80,
    *,
    page: int | None = None,
    section: str | None = None,
    kind: str = "paragraph",
    document_hash: str | None = None,
    start_index: int = 0,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if chunk_size_words < 20:
        raise ValueError("chunk_size_words must be at least 20")
    if overlap_words < 0 or overlap_words >= chunk_size_words:
        raise ValueError("overlap_words must be non-negative and smaller than chunk_size_words")
    words = (text or "").split()
    if not words:
        return []
    digest = document_hash or text_hash(text)
    chunks: list[dict[str, Any]] = []
    step = max(1, chunk_size_words - overlap_words)
    search_offset = 0
    for relative_index, start in enumerate(range(0, len(words), step)):
        segment = words[start : start + chunk_size_words]
        if not segment:
            break
        chunk_value = " ".join(segment)
        text_start = text.find(segment[0], search_offset) if segment else -1
        text_start = max(0, text_start)
        text_end = min(len(text), text_start + len(chunk_value))
        search_offset = text_start + max(1, len(chunk_value) - 20)
        index = start_index + relative_index
        chunk_hash = text_hash(chunk_value)
        item = {
            "source_name": source_title(filename),
            "filename": filename,
            "chunk_text": chunk_value,
            "chunk_index": index,
            "chunk_id": f"{digest[:12]}-{index:05d}-{chunk_hash[:8]}",
            "content_hash": chunk_hash,
            "document_hash": digest,
            "page": page,
            "section": section,
            "kind": kind,
            "text_start": text_start,
            "text_end": text_end,
        }
        item.update(metadata or {})
        chunks.append(item)
        if start + chunk_size_words >= len(words):
            break
    return chunks


def chunk_document(
    document: dict[str, Any],
    *,
    chunk_size_words: int = 650,
    overlap_words: int = 80,
) -> list[dict[str, Any]]:
    filename = str(document["filename"])
    digest = str(document.get("content_hash") or text_hash(str(document.get("text", ""))))
    blocks = list(document.get("blocks") or [])
    if not blocks:
        return chunk_text(
            str(document.get("text", "")),
            filename,
            chunk_size_words,
            overlap_words,
            document_hash=digest,
        )
    chunks: list[dict[str, Any]] = []
    for block in blocks:
        metadata = {
            key: value for key, value in block.items() if key not in {"text", "filename", "page", "section", "kind"}
        }
        block_chunks = chunk_text(
            str(block.get("text", "")),
            filename,
            chunk_size_words,
            overlap_words,
            page=block.get("page"),
            section=block.get("section"),
            kind=str(block.get("kind", "paragraph")),
            document_hash=digest,
            start_index=len(chunks),
            metadata=metadata,
        )
        chunks.extend(block_chunks)
    return chunks


def chunk_documents(
    documents: list[dict[str, Any]],
    *,
    chunk_size_words: int = 650,
    overlap_words: int = 80,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for document in documents:
        digest = str(document.get("content_hash") or text_hash(str(document.get("text", ""))))
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        chunks.extend(
            chunk_document(
                document,
                chunk_size_words=chunk_size_words,
                overlap_words=overlap_words,
            )
        )
    return chunks
