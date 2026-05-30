from __future__ import annotations

from src.utils import source_title


def chunk_text(
    text: str,
    filename: str,
    chunk_size_words: int = 650,
    overlap_words: int = 80,
) -> list[dict]:
    words = (text or "").split()
    if not words:
        return []

    chunks = []
    step = max(1, chunk_size_words - overlap_words)
    for index, start in enumerate(range(0, len(words), step)):
        segment = words[start : start + chunk_size_words]
        if not segment:
            break
        chunks.append(
            {
                "source_name": source_title(filename),
                "filename": filename,
                "chunk_text": " ".join(segment),
                "chunk_index": index,
            }
        )
        if start + chunk_size_words >= len(words):
            break
    return chunks


def chunk_documents(documents: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for document in documents:
        chunks.extend(chunk_text(document["text"], document["filename"]))
    return chunks
