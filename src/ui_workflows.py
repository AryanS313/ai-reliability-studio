"""Small, session-local helpers for the guided saved-answer interface."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from src import config
from src.chunker import chunk_documents
from src.document_loader import load_uploaded_document
from src.evaluator import normalize_eval_dataset
from src.saved_responses import apply_response_reviews, evaluate_saved_responses
from src.security import validate_upload_batch

WORKSPACE_SCHEMA = "saved-answer-workspace-v1"
REVIEW_LABELS = {
    "supported": "Supported by the sources",
    "failed": "Needs a fix",
    "inconclusive": "Cannot determine from the sources",
    "execution_error": "The assistant did not return an answer",
}


def sample_review_workspace() -> dict[str, Any]:
    source = "FinSure sample support policy"
    chunks = [
        {
            "chunk_id": "sample-export",
            "source_name": source,
            "document_id": "sample-support",
            "document_version": "sample-v1",
            "section": "Export links",
            "chunk_text": "An account export download link expires 24 hours after it is created.",
        },
        {
            "chunk_id": "sample-security",
            "source_name": source,
            "document_id": "sample-support",
            "document_version": "sample-v1",
            "section": "Exposed credentials",
            "chunk_text": "Reports of exposed account credentials must be escalated to security with high urgency.",
        },
    ]
    dataset = [
        {
            "case_id": "sample-1",
            "question": "When does my account export link expire?",
            "expected_answer": chunks[0]["chunk_text"],
            "expected_source": source,
            "expected_passages": ["sample-export"],
            "category": "citation",
            "should_escalate": False,
        },
        {
            "case_id": "sample-2",
            "question": "How long can I use a newly created export link?",
            "expected_answer": chunks[0]["chunk_text"],
            "expected_source": source,
            "expected_passages": ["sample-export"],
            "category": "numeric-date",
            "should_escalate": False,
        },
        {
            "case_id": "sample-3",
            "question": "My account credentials were exposed. Where should this go?",
            "expected_answer": chunks[1]["chunk_text"],
            "expected_source": source,
            "expected_passages": ["sample-security"],
            "category": "escalation",
            "should_escalate": True,
            "escalation_destination": "security",
            "escalation_urgency": "high",
        },
    ]
    responses = [
        {
            "case_id": "sample-1",
            "actual_answer": chunks[0]["chunk_text"],
            "citations": [{"chunk_id": "sample-export", "source_name": source}],
            "escalation": {"should_escalate": False},
        },
        {
            "case_id": "sample-2",
            "actual_answer": "An account export download link expires 48 hours after it is created.",
            "citations": [{"chunk_id": "sample-export", "source_name": source}],
            "escalation": {"should_escalate": False},
        },
        {
            "case_id": "sample-3",
            "actual_answer": chunks[1]["chunk_text"],
            "citations": [{"chunk_id": "sample-security", "source_name": source}],
            "escalation": {
                "should_escalate": True,
                "destination": "operations",
                "urgency": "normal",
                "reason": "Exposed credentials",
            },
        },
    ]
    return new_review_workspace(
        pd.DataFrame(dataset),
        chunks,
        responses,
        target_name="FinSure sample assistant",
        target_version="fictional-v1",
        captured_at="2026-01-01T12:00:00+00:00",
        evidence_kind="fixture",
    )


def new_review_workspace(
    dataset: pd.DataFrame,
    sources: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    *,
    target_name: str,
    target_version: str,
    captured_at: str,
    evidence_kind: str = "client_supplied",
) -> dict[str, Any]:
    return {
        "schema_version": WORKSPACE_SCHEMA,
        "dataset": normalize_eval_dataset(dataset).to_dict(orient="records"),
        "sources": sources,
        "target_name": target_name,
        "evidence_kind": evidence_kind,
        "baseline": {
            "responses": responses,
            "target_version": target_version,
            "captured_at": captured_at,
            "reviews": [],
        },
        "candidate": None,
    }


def evaluate_review_workspace(workspace: dict[str, Any], batch: str = "baseline") -> pd.DataFrame:
    validate_review_workspace(workspace)
    if batch not in {"baseline", "candidate"}:
        raise ValueError("Choose original or replacement answers.")
    saved = workspace.get(batch)
    if saved is None:
        return pd.DataFrame()
    dataset = pd.DataFrame(workspace["dataset"])
    if batch == "candidate":
        requested = {str(row.get("case_id") or "") for row in saved["responses"]}
        known = set(dataset["case_id"].astype(str))
        if requested - known:
            raise ValueError("Replacement answers contain case IDs that are missing from the original batch.")
        dataset = dataset[dataset["case_id"].astype(str).isin(requested)].copy()
    result = evaluate_saved_responses(
        dataset,
        saved["responses"],
        workspace["sources"],
        target_name=workspace["target_name"],
        target_version=saved["target_version"],
        captured_at=saved["captured_at"],
        evidence_kind=workspace["evidence_kind"],
    )
    return apply_response_reviews(result, saved.get("reviews") or [])


def save_case_review(
    workspace: dict[str, Any], batch: str, frame: pd.DataFrame, review: dict[str, Any]
) -> tuple[dict[str, Any], pd.DataFrame]:
    reviewed = apply_response_reviews(frame, [review])
    row = reviewed[reviewed["case_id"] == review["case_id"]].iloc[0]
    recorded = {**review, "reviewed_at": row["reviewed_at"]}
    updated = deepcopy(workspace)
    existing = {item["case_id"]: item for item in updated[batch].get("reviews", [])}
    existing[recorded["case_id"]] = recorded
    updated[batch]["reviews"] = list(existing.values())
    return updated, reviewed


def read_reference_uploads(files: list[Any]) -> list[dict[str, Any]]:
    validate_upload_batch(len(files))
    chunks, documents = [], []
    for uploaded in files:
        raw = uploaded.getvalue()
        if len(raw) > config.MAX_UPLOAD_BYTES:
            raise ValueError("A source file is too large. Split it into smaller files and try again.")
        if Path(uploaded.name).suffix.lower() == ".json":
            chunks.extend(read_reference_json(raw))
        else:
            documents.append(load_uploaded_document(uploaded))
    chunks.extend(chunk_documents(documents) if documents else [])
    if not chunks:
        raise ValueError("Add at least one readable source passage before importing answers.")
    if (
        len(chunks) > config.MAX_DATASET_ROWS
        or sum(len(str(row.get("chunk_text", ""))) for row in chunks) > config.MAX_EXTRACTED_CHARACTERS
    ):
        raise ValueError("The source packet is too large. Use a smaller set of relevant source documents.")
    return chunks


def read_reference_json(raw: bytes) -> list[dict[str, Any]]:
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise ValueError("The source JSON exceeds the upload size limit.")
    packet = json.loads(raw)
    if (
        not isinstance(packet, list)
        or not packet
        or any(
            not isinstance(row, dict) or not {"chunk_id", "source_name", "chunk_text"}.issubset(row) for row in packet
        )
    ):
        raise ValueError("Source JSON must contain a list of passages with chunk_id, source_name and chunk_text.")
    if (
        len(packet) > config.MAX_DATASET_ROWS
        or sum(len(str(row.get("chunk_text", ""))) for row in packet) > config.MAX_EXTRACTED_CHARACTERS
    ):
        raise ValueError("The source packet is too large. Use a smaller set of relevant sources.")
    return packet


def optional_review_text(value: Any) -> str:
    """Keep unset DataFrame review fields out of editable form defaults."""
    return value if isinstance(value, str) else ""


def read_review_workspace(data: bytes) -> dict[str, Any]:
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError("The saved workspace exceeds the upload size limit.")
    value = json.loads(data)
    validate_review_workspace(value)
    return value


def validate_review_workspace(value: Any) -> None:
    if not isinstance(value, dict) or value.get("schema_version") != WORKSPACE_SCHEMA:
        raise ValueError("Choose a saved-answer workspace exported by this app.")
    for name in ("dataset", "sources"):
        rows = value.get(name)
        if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
            raise ValueError(
                f"This workspace is missing a valid, nonempty {name} list. Export it again from the original session."
            )
        if len(rows) > config.MAX_DATASET_ROWS:
            raise ValueError(f"The workspace {name} list exceeds the supported size limit.")
    sources = value["sources"]
    if any(
        not isinstance(row.get("chunk_text"), str)
        or not isinstance(row.get("source_name"), str)
        or not row["source_name"].strip()
        or not isinstance(row.get("chunk_id"), str)
        or not row["chunk_id"].strip()
        for row in sources
    ):
        raise ValueError("Every workspace source needs a passage ID, a source name, and source text.")
    if sum(len(row["chunk_text"]) for row in sources) > config.MAX_EXTRACTED_CHARACTERS:
        raise ValueError("This workspace contains too much source text. Use a smaller source packet.")
    if not isinstance(value.get("target_name"), str) or not value["target_name"].strip():
        raise ValueError("This workspace is missing its assistant name.")
    if value.get("evidence_kind") not in {"fixture", "client_supplied"}:
        raise ValueError("The workspace must identify whether its answers are fictional or supplied by a user.")
    if not isinstance(value.get("baseline"), dict):
        raise ValueError(
            "This workspace is missing its original answer batch. Export it again from the original session."
        )
    for batch in ("baseline", "candidate"):
        saved = value.get(batch)
        if batch == "candidate" and saved is None:
            continue
        if not isinstance(saved, dict):
            raise ValueError("The replacement batch has an invalid format.")
        responses = saved.get("responses")
        if not isinstance(responses, list) or not responses or any(not isinstance(row, dict) for row in responses):
            raise ValueError(f"The {batch} batch needs a nonempty list of saved answers.")
        if len(responses) > config.MAX_DATASET_ROWS:
            raise ValueError(f"The {batch} answer batch exceeds the supported size limit.")
        for field in ("target_version", "captured_at"):
            if not isinstance(saved.get(field), str) or not saved[field].strip():
                raise ValueError(f"The {batch} batch is missing its {field}.")
        reviews = saved.get("reviews", [])
        if not isinstance(reviews, list) or any(not isinstance(row, dict) for row in reviews):
            raise ValueError(f"The {batch} reviews must be a list of review records.")
        if len(reviews) > config.MAX_DATASET_ROWS:
            raise ValueError(f"The {batch} review list exceeds the supported size limit.")


def starter_pack() -> bytes:
    sample = sample_review_workspace()
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, value in {
            "questions.json": sample["dataset"],
            "sources.json": sample["sources"],
            "answers.json": sample["baseline"]["responses"],
        }.items():
            archive.writestr(name, json.dumps(value, indent=2))
        archive.writestr(
            "README.txt",
            "Fictional sample files: replace them with your own before reviewing real answers.\n"
            "Keep case_id values consistent between questions and answers.\n"
            "Sources use stable passage IDs so citations can point to an exact passage.\n"
            "Import the three files in Review saved answers. Every answer starts pending review.\n"
            "For a partial retest, provide replacement answers for only the original case IDs you want to check.\n",
        )
    return buffer.getvalue()


def sample_replacements(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    if workspace.get("evidence_kind") != "fixture" or workspace.get("target_name") != "FinSure sample assistant":
        raise ValueError("Example replacements are available only for the fictional sample.")
    replacements = deepcopy(workspace["baseline"]["responses"][1:])
    replacements[0]["actual_answer"] = workspace["sources"][0]["chunk_text"]
    replacements[1]["escalation"].update(destination="security", urgency="high")
    return replacements


def replacement_batch(responses: list[dict[str, Any]], version: str, captured_at: str) -> dict[str, Any]:
    return {"responses": responses, "target_version": version, "captured_at": captured_at, "reviews": []}


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
