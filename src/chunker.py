from __future__ import annotations

import re
from typing import Any

from src.document_loader import source_extraction_warnings
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
    words = list(re.finditer(r"\S+", text or ""))
    if not words:
        return []
    digest = document_hash or text_hash(text)
    chunks: list[dict[str, Any]] = []
    step = max(1, chunk_size_words - overlap_words)
    for relative_index, start in enumerate(range(0, len(words), step)):
        segment = words[start : start + chunk_size_words]
        if not segment:
            break
        text_start = segment[0].start()
        text_end = segment[-1].end()
        chunk_value = text[text_start:text_end]
        index = start_index + relative_index
        chunk_hash = text_hash(chunk_value)
        item = {
            **(metadata or {}),
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
            "text_span_scope": "provided_text",
        }
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
    notices = source_extraction_warnings([document])
    warning_metadata = {"extraction_warnings": notices, "partially_extracted": True} if notices else {}
    blocks = list(document.get("blocks") or [])
    if not blocks:
        chunks = chunk_text(
            str(document.get("text", "")),
            filename,
            chunk_size_words,
            overlap_words,
            document_hash=digest,
            metadata=warning_metadata,
        )
        for chunk in chunks:
            chunk["text_span_scope"] = "document"
        return chunks
    chunks = []
    document_text = str(document.get("text", ""))
    search_offset = 0
    for block_index, block in enumerate(blocks):
        block_text = str(block.get("text", ""))
        document_start = document_text.find(block_text, search_offset) if block_text else -1
        if document_start >= 0:
            search_offset = document_start + len(block_text)
        metadata = {
            key: value for key, value in block.items() if key not in {"text", "filename", "page", "section", "kind"}
        }
        metadata.update(warning_metadata)
        block_chunks = chunk_text(
            block_text,
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
        for chunk in block_chunks:
            chunk["block_index"] = block_index
            chunk["text_span_scope"] = "document" if document_start >= 0 else "block"
            if document_start >= 0:
                chunk["text_start"] += document_start
                chunk["text_end"] += document_start
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
    warnings_by_document: dict[str, list[str]] = {}
    for document in documents:
        digest = str(document.get("content_hash") or text_hash(str(document.get("text", ""))))
        notices = source_extraction_warnings([document])
        if notices:
            warnings_by_document[digest] = source_extraction_warnings(
                [{"extraction_warnings": [*warnings_by_document.get(digest, []), *notices]}]
            )
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
    for chunk in chunks:
        chunk_notices = warnings_by_document.get(str(chunk.get("document_hash")))
        if chunk_notices:
            chunk["extraction_warnings"] = list(chunk_notices)
            chunk["partially_extracted"] = True
    return chunks
