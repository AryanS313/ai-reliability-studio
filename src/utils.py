from __future__ import annotations

import hashlib
import re
from pathlib import Path


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_title(filename: str) -> str:
    stem = Path(filename).stem
    return stem.replace("_", " ").replace("-", " ").title()


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def keyword_tokens(text: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "be",
        "by",
        "can",
        "for",
        "from",
        "if",
        "in",
        "is",
        "it",
        "must",
        "no",
        "not",
        "of",
        "or",
        "should",
        "the",
        "to",
        "when",
        "with",
        "yes",
    }
    return {tok for tok in normalize_text(text).split() if len(tok) > 2 and tok not in stop_words}


def format_context(chunks: list[dict]) -> str:
    lines = []
    for chunk in chunks:
        source = chunk.get("source_name", "Unknown Source")
        score = chunk.get("similarity", 0)
        lines.append(f"[Source: {source} | Similarity: {score:.2f}]\n{chunk.get('chunk_text', '')}")
    return "\n\n".join(lines)

