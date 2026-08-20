from __future__ import annotations

import io
import zipfile

import pytest

from src.chunker import chunk_document
from src.document_loader import (
    detect_duplicate_documents,
    extract_document_artifact,
    extract_document_bytes,
)
from src.infrastructure import (
    MalwareScanner,
    OCRPipeline,
    OCRResult,
    ScanResult,
    ScanVerdict,
    UnavailableMalwareScanner,
)
from src.retrieval import retrieval_metrics
from src.security import UploadSecurityError
from src.vector_store import SimpleVectorStore


def test_structural_chunking_preserves_page_section_and_ids():
    document = {
        "filename": "policy.md",
        "text": "# Refunds\n\nRefunds require review.",
        "content_hash": "a" * 64,
        "blocks": [
            {"text": "Refunds require review after 7 days.", "kind": "paragraph", "page": 3, "section": "Refunds"}
        ],
    }
    chunks = chunk_document(document, chunk_size_words=20, overlap_words=2)
    assert chunks[0]["page"] == 3
    assert chunks[0]["section"] == "Refunds"
    assert chunks[0]["chunk_id"].startswith("aaaaaaaaaaaa")
    assert chunks[0]["text_end"] > chunks[0]["text_start"]


def test_hybrid_retrieval_threshold_filters_and_metrics_are_independent():
    chunks = [
        {"chunk_id": "refund", "source_name": "Refund Policy", "chunk_text": "Refunds after 7 days need review."},
        {"chunk_id": "kyc", "source_name": "KYC Policy", "chunk_text": "KYC requires identity documents."},
    ]
    store = SimpleVectorStore()
    store.build(chunks)
    results = store.retrieve("refund after seven days", top_k=2, similarity_threshold=0.01)
    assert results[0]["chunk_id"] == "refund"
    assert "semantic_score" in results[0] and "lexical_score" in results[0]
    metrics = retrieval_metrics(results, expected_sources=["Refund Policy"], relevant_chunk_ids=["refund"])
    assert metrics["hit_rate"] == 1
    assert metrics["mrr"] == 1
    assert metrics["precision_at_k"] >= 0.5


def test_html_is_sanitized_and_extraction_reports_provenance():
    artifact = extract_document_artifact(
        "policy.html",
        b"<h1>Policy</h1><script>steal()</script><p>Review required</p>",
    )
    assert "steal" not in artifact["text"]
    assert artifact["blocks"][0]["section"] == "Policy"
    assert artifact["content_hash"]


def test_malformed_office_archive_and_unsafe_filename_are_rejected():
    with pytest.raises(ValueError, match="Malformed Office archive"):
        extract_document_bytes("broken.docx", b"not-a-zip")
    with pytest.raises(UploadSecurityError):
        extract_document_bytes("..", b"content")


def test_exact_and_near_duplicates_are_reported():
    documents = [
        {"filename": "a.md", "text": "Policy requires review", "content_hash": "same"},
        {"filename": "b.md", "text": "Policy requires review", "content_hash": "same"},
    ]
    findings = detect_duplicate_documents(documents)
    assert findings == [{"document": "b.md", "duplicate_of": "a.md", "type": "exact", "similarity": 1.0}]


def test_zip_decompression_limit_is_enforced(monkeypatch):
    from src import config

    monkeypatch.setattr(config, "MAX_EXTRACTED_CHARACTERS", 10)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "x" * 10000)
    with pytest.raises(ValueError, match="decompression safety"):
        extract_document_artifact("large.docx", buffer.getvalue())


class MaliciousScanner(MalwareScanner):
    production_ready = True

    def scan(self, content: bytes, filename: str) -> ScanResult:
        return ScanResult(ScanVerdict.MALICIOUS, "test-scanner", "1")


class FakeOCR(OCRPipeline):
    production_ready = True

    def extract(self, content: bytes, *, filename: str, language: str | None = None) -> OCRResult:
        return OCRResult(True, "OCR policy text", "test-ocr")


def test_document_ingestion_scan_is_explicit_and_production_fails_closed(monkeypatch):
    development = extract_document_artifact("policy.txt", b"Policy text")
    assert development["malware_scan"]["verdict"] == "not_requested"
    assert development["malware_scan"]["production_ready"] is False

    unavailable = extract_document_artifact("policy.txt", b"Policy text", malware_scanner=UnavailableMalwareScanner())
    assert unavailable["malware_scan"]["verdict"] == "unavailable"
    assert unavailable["partially_extracted"] is True
    with pytest.raises(ValueError, match="rejected by malware"):
        extract_document_artifact("policy.txt", b"Policy text", malware_scanner=MaliciousScanner())

    monkeypatch.setattr("src.config.REQUIRE_MALWARE_SCAN", True)
    with pytest.raises(ValueError, match="requires a configured malware scanner"):
        extract_document_artifact("policy.txt", b"Policy text")
    with pytest.raises(ValueError, match="fail-closed"):
        extract_document_artifact("policy.txt", b"Policy text", malware_scanner=UnavailableMalwareScanner())
