"""Review chunks must be exact source substrings with interpretable coordinates."""

import re

import pytest

from src.chunker import chunk_document, chunk_documents, chunk_text
from src.document_loader import source_extraction_warnings


def test_table_rows_and_unicode_spacing_survive_in_review_text():
    text = "\nPlan | Retention\nBasic | 30\u00a0days\nPro | 90\u2003days\n"
    chunks = chunk_text(text, "retention.md", chunk_size_words=20, overlap_words=2, kind="table")
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["chunk_text"] == text.strip()
    assert text[chunk["text_start"] : chunk["text_end"]] == chunk["chunk_text"]


@pytest.mark.parametrize("overlap", [0, 6, 19])
def test_repeated_words_have_exact_spans_and_unchanged_word_window_overlap(overlap):
    separators = ["  ", "\n", "\t", "\u00a0", "\n\n"]
    text = "  " + "".join(f"renew{separators[index % len(separators)]}" for index in range(60))
    words = list(re.finditer(r"\S+", text))
    chunks = chunk_text(text, "renewals.txt", chunk_size_words=20, overlap_words=overlap, start_index=7)
    expected_starts = []
    for start in range(0, len(words), 20 - overlap):
        expected_starts.append(start)
        if start + 20 >= len(words):
            break
    assert len(chunks) == len(expected_starts)
    for index, (chunk, start) in enumerate(zip(chunks, expected_starts, strict=True)):
        stop = min(len(words), start + 20)
        assert chunk["text_start"] == words[start].start()
        assert chunk["text_end"] == words[stop - 1].end()
        assert chunk["chunk_text"] == text[words[start].start() : words[stop - 1].end()]
        assert len(chunk["chunk_text"].split()) == stop - start
        assert chunk["chunk_index"] == index + 7


def test_structural_chunks_have_exact_document_coordinates_when_blocks_are_present():
    introduction = "Review the applicable plan before quoting retention."
    table = "Plan | Days\nBasic | 30\nPro | 90"
    exception = "A legal hold overrides automatic deletion."
    text = f"{introduction}\n\n{table}\n\n{exception}"
    document = {
        "filename": "retention.md",
        "text": text,
        "blocks": [
            {"text": introduction, "kind": "paragraph"},
            {"text": table, "kind": "table", "section": "Retention"},
            {"text": exception, "kind": "paragraph"},
        ],
    }
    chunks = chunk_document(document, chunk_size_words=20, overlap_words=2)
    assert len(chunks) == 3
    for index, chunk in enumerate(chunks):
        assert chunk["text_span_scope"] == "document"
        assert chunk["block_index"] == index
        assert text[chunk["text_start"] : chunk["text_end"]] == chunk["chunk_text"]
    assert chunks[1]["chunk_text"] == table
    assert chunks[1]["section"] == "Retention"


def test_unmapped_structural_block_uses_explicit_block_coordinates_without_guessing():
    block_text = "A separately extracted table retains its own source coordinates."
    document = {
        "filename": "structured.pdf",
        "text": "The flattened display text is different.",
        "blocks": [{"text": block_text, "kind": "table", "page": 2}],
    }
    chunk = chunk_document(document, chunk_size_words=20, overlap_words=2)[0]
    assert chunk["text_span_scope"] == "block"
    assert chunk["block_index"] == 0
    assert block_text[chunk["text_start"] : chunk["text_end"]] == chunk["chunk_text"]
    assert chunk["page"] == 2


def test_auxiliary_metadata_cannot_override_derived_text_or_span():
    text = "Policy records remain available for thirty days."
    chunk = chunk_text(
        text,
        "policy.txt",
        chunk_size_words=20,
        overlap_words=2,
        metadata={"text_start": 900, "text_end": 999, "chunk_text": "Invented", "sheet": "Plan"},
    )[0]
    assert chunk["chunk_text"] == text
    assert text[chunk["text_start"] : chunk["text_end"]] == text
    assert chunk["sheet"] == "Plan"


@pytest.mark.parametrize("structured", [False, True])
def test_live_document_chunks_keep_extraction_notices_and_exact_spans(structured):
    text = "Plan | Days\nBasic | 30\nPro | 90"
    document = {
        "filename": "policy.pdf",
        "text": text,
        "warnings": ["Page 2 contains no searchable text."],
        "partially_extracted": True,
    }
    if structured:
        document["blocks"] = [{"text": text, "kind": "table", "page": 1}]
    chunks = chunk_document(document, chunk_size_words=20, overlap_words=2)
    assert source_extraction_warnings(chunks) == ["policy.pdf: Page 2 contains no searchable text."]
    for chunk in chunks:
        assert chunk["partially_extracted"] is True
        assert chunk["text_span_scope"] == "document"
        assert text[chunk["text_start"] : chunk["text_end"]] == chunk["chunk_text"]


def test_live_duplicate_documents_merge_notices_without_replacing_source_spans():
    text = "The Basic plan keeps records for 30 days."
    original = {"filename": "first.txt", "text": text, "warnings": []}
    duplicate = {
        "filename": "second.pdf",
        "text": text,
        "warnings": ["Page 2 contains no searchable text."],
    }
    chunks = chunk_documents([original, duplicate])
    assert len(chunks) == 1
    assert chunks[0]["filename"] == "first.txt"
    assert chunks[0]["partially_extracted"] is True
    assert source_extraction_warnings(chunks) == ["second.pdf: Page 2 contains no searchable text."]
    assert text[chunks[0]["text_start"] : chunks[0]["text_end"]] == chunks[0]["chunk_text"]
    assert original["warnings"] == []
