"""Offline response review with explicit evidence, reviewer, and comparison boundaries.

This path scores supplied answers against a fixed reference corpus. It never
contacts a provider, infers the client's retrieval, or issues a launch verdict.
An automatic pass does not complete review: every case starts pending.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from src import config
from src.calibration import EvaluatorThresholdConfiguration
from src.domain import ExecutionStatus, TargetType
from src.evaluator import normalize_eval_dataset
from src.scoring import EVALUATOR_VERSION, LABEL_SEMANTICS_VERSION, score_result
from src.security import redact_pii, redact_secrets
from src.versioning import runtime_metadata, version_hash

REVIEW_DECISIONS = {"supported", "failed", "inconclusive", "execution_error"}
REVIEWER_KINDS = {"ai_assisted", "human"}
RESPONSE_STATUSES = {status.value for status in ExecutionStatus} - {"pending", "running"}
REFERENCE_REVIEW_WEIGHTS = {
    "correctness": 0.375,
    "retrieval": 0.0,
    "citation": 0.25,
    "groundedness": 0.25,
    "escalation": 0.125,
}


def read_response_file(filename: str, data: bytes) -> list[dict[str, Any]]:
    """Read bounded JSON/JSONL/CSV records without evaluating or trusting content."""
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError("Response/review file exceeds the configured upload size limit.")
    text = data.decode("utf-8-sig")
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        value = json.loads(text)
    elif suffix == ".jsonl":
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif suffix == ".csv":
        reader = csv.DictReader(StringIO(text))
        names = reader.fieldnames or []
        if len(names) != len(set(names)):
            raise ValueError("CSV contains duplicate column names.")
        value = list(reader)
        for row in value:
            if None in row:
                raise ValueError("CSV row contains more values than column names.")
            for key in ("citations", "escalation", "metadata"):
                if row.get(key):
                    row[key] = json.loads(row[key])
    else:
        raise ValueError("Response/review files must be JSON, JSONL, or CSV.")
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Response/review file must contain a list of objects.")
    if len(value) > config.MAX_DATASET_ROWS:
        raise ValueError("Response/review record count exceeds the configured limit.")
    return value


def _indexed(records: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    if len(records) > config.MAX_DATASET_ROWS:
        raise ValueError(f"{name} exceeds the configured record count limit.")
    indexed: dict[str, dict[str, Any]] = {}
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str) or not row["case_id"].strip():
            raise ValueError(f"Every {name} record requires a nonempty string case_id.")
        case_id = row["case_id"].strip()
        if case_id in indexed:
            raise ValueError(f"Duplicate {name} case_id: {case_id}")
        indexed[case_id] = row
    return indexed


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp with a timezone.")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp with a timezone.") from exc
    if stamp.tzinfo is None:
        raise ValueError(f"{field} must include a timezone.")
    return stamp.isoformat()


def _optional_measurement(value: Any, name: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite nonnegative number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite nonnegative number.") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite nonnegative number.")
    return number


def _validated_response(row: dict[str, Any]) -> dict[str, Any]:
    status = row.get("execution_status", "passed")
    if status not in RESPONSE_STATUSES:
        raise ValueError(f"Invalid execution_status for case {row['case_id']}.")
    answer = row.get("actual_answer", row.get("answer", ""))
    if not isinstance(answer, str) or (status == "passed" and not answer.strip()):
        raise ValueError(f"Successful response {row['case_id']} requires nonempty actual_answer text.")
    citations = row.get("citations") or []
    escalation = row.get("escalation") or None
    if not isinstance(citations, list) or any(not isinstance(citation, dict) for citation in citations):
        raise ValueError(f"Citations for {row['case_id']} must be a list of objects.")
    if escalation is not None and not isinstance(escalation, dict):
        raise ValueError(f"Escalation for {row['case_id']} must be an object.")
    return {
        **row,
        "execution_status": status,
        "actual_answer": answer,
        "citations": citations,
        "escalation": escalation,
        "latency_ms": _optional_measurement(row.get("latency_ms"), "latency_ms"),
        "estimated_cost": _optional_measurement(row.get("estimated_cost", row.get("cost")), "estimated_cost"),
    }


def evaluate_saved_responses(
    eval_df: pd.DataFrame,
    response_records: list[dict[str, Any]],
    source_chunks: list[dict[str, Any]],
    *,
    target_name: str,
    target_version: str,
    captured_at: str,
    evidence_kind: str = "client_supplied",
) -> pd.DataFrame:
    """Evaluate an exact case/response set; leave all source reviews pending.

    The capture time and target version are supplied provenance, not independently
    attested facts. For partial retests pass the explicitly selected dataset rows.
    Reference-source checks are distinct from the client's unobserved retrieval.
    """
    if evidence_kind not in {"client_supplied", "fixture"}:
        raise ValueError("evidence_kind must be client_supplied or fixture.")
    if not target_name.strip() or not target_version.strip():
        raise ValueError("An explicit target_name and target_version are required.")
    captured = _timestamp(captured_at, "captured_at")
    if eval_df.empty:
        raise ValueError("At least one evaluation case is required.")
    dataset = normalize_eval_dataset(eval_df)
    cases = _indexed(dataset.to_dict(orient="records"), "dataset")
    responses = _indexed(response_records, "response")
    if set(cases) != set(responses):
        raise ValueError(
            f"Case/response sets differ: missing={sorted(set(cases) - set(responses))}; "
            f"unexpected={sorted(set(responses) - set(cases))}. Select an explicit dataset subset for retests."
        )
    source_ids = [str(chunk.get("chunk_id") or "") for chunk in source_chunks]
    if any(not chunk_id for chunk_id in source_ids) or len(source_ids) != len(set(source_ids)):
        raise ValueError("Every reference chunk requires a unique chunk_id.")
    for chunk in source_chunks:
        if not isinstance(chunk.get("chunk_text"), str) or not str(chunk.get("source_name") or "").strip():
            raise ValueError("Every reference chunk requires chunk_text and source_name.")
    source_snapshot = sorted(source_chunks, key=lambda chunk: str(chunk["chunk_id"]))
    source_version = version_hash(source_snapshot)
    dataset_version = version_hash(list(cases.values()))
    response_batch_version = version_hash(response_records)
    imported_at = datetime.now(UTC).isoformat()
    thresholds = EvaluatorThresholdConfiguration()
    manifest: dict[str, Any] = {
        "schema_version": "saved-response-review-v1",
        "created_at": imported_at,
        "environment": "offline_review",
        "runtime": runtime_metadata(),
        "evidence_kind": evidence_kind,
        "target": {"type": TargetType.SAVED_RESPONSES.value, "name": target_name, "version": target_version},
        "capture": {"reported_at": captured, "independently_verified": False},
        "dataset": {"content_hash": dataset_version, "case_count": len(cases)},
        "responses": {"content_hash": response_batch_version, "record_count": len(responses)},
        "knowledge_base": {"content_hash": source_version, "chunk_count": len(source_snapshot)},
        "reference_chunks": source_snapshot,
        "evaluators": {
            "version": EVALUATOR_VERSION,
            "weights": REFERENCE_REVIEW_WEIGHTS,
            "threshold_version": thresholds.version,
            "thresholds": thresholds.thresholds,
        },
        "client_retrieval_status": "not_measured",
        "measurement_provenance": "Optional latency and cost are client-reported; missing values remain unknown.",
        "review_policy": "Every case needs a separate review; automatic passing is not a reviewed decision.",
        "snapshot_redaction": "Secret patterns are removed before the manifest is hashed; input content hashes identify the supplied originals.",
    }
    manifest = redact_secrets(manifest)
    manifest["manifest_hash"] = version_hash(manifest)
    rows: list[dict[str, Any]] = []
    for case_id, case in cases.items():
        if not isinstance(case.get("should_escalate"), bool):
            raise ValueError(f"Case {case_id} requires an explicit should_escalate expectation.")
        response = _validated_response(responses[case_id])
        if response.get("target_version", target_version) != target_version:
            raise ValueError(f"Response target version differs from batch version for {case_id}.")
        if response.get("captured_at"):
            _timestamp(response["captured_at"], "response captured_at")
        reference = str(case.get("expected_answer") or next(iter(case.get("expected_answers") or []), ""))
        expected_source = str(case.get("expected_source") or next(iter(case.get("expected_sources") or []), ""))
        row: dict[str, Any] = {
            **case,
            "case_id": case_id,
            "case_version": version_hash(case),
            "response_hash": version_hash(responses[case_id]),
            "response_batch_version": response_batch_version,
            "actual_answer": response["actual_answer"],
            "execution_status": response["execution_status"],
            "captured_at": response.get("captured_at", captured),
            "run_timestamp": imported_at,
            "run_id": f"offline-{manifest['manifest_hash'][:16]}",
            "manifest": manifest,
            "manifest_hash": manifest["manifest_hash"],
            "dataset_version": dataset_version,
            "knowledge_base_version": source_version,
            "document_versions": sorted(
                {
                    str(chunk.get("document_version") or chunk.get("document_hash") or "unknown")
                    for chunk in source_chunks
                }
            ),
            "target_type": TargetType.SAVED_RESPONSES.value,
            "target_name": target_name,
            "target_version": target_version,
            "model_name": str(response.get("model") or "not_reported"),
            "provider": str(response.get("provider") or "not_reported"),
            "evidence_kind": evidence_kind,
            "environment": "offline_review",
            "candidate_id": version_hash({"target_name": target_name, "target_version": target_version}),
            "candidate_name": f"{target_name} · saved responses",
            "evaluator_version": EVALUATOR_VERSION,
            "threshold_version": thresholds.version,
            "label_semantics_version": LABEL_SEMANTICS_VERSION,
            "calibration_status": "insufficiently_calibrated",
            "dataset_launch_eligible": False,
            "human_review_status": "not_reviewed",
            "review_status": "pending",
            "review_decision": None,
            "reference_chunks": source_chunks,
            "provided_citations": response["citations"],
            "structured_escalation": response["escalation"],
        }
        if response["execution_status"] == "passed":
            scores = score_result(
                actual_answer=response["actual_answer"],
                expected_answer=reference,
                expected_answers=list(case.get("expected_answers") or []),
                expected_source=expected_source,
                should_escalate=bool(case.get("should_escalate")),
                expected_destination=str(case.get("escalation_destination") or "") or None,
                expected_urgency=str(case.get("escalation_urgency") or "") or None,
                retrieved_chunks=source_chunks,
                provided_citations=response["citations"],
                structured_escalation=response["escalation"],
                unacceptable_answers=list(case.get("unacceptable_answers") or []),
                rubric=dict(case.get("rubric") or {}),
                weights=REFERENCE_REVIEW_WEIGHTS,
                evaluator_thresholds=thresholds.thresholds,
                latency_ms=0,
                estimated_cost=0,
            )
            row.update(scores)
            # These checks use a supplied reference corpus, not observed retrieval.
            missing_source = "retrieval_failure" in row.get("failure_labels", [])
            row["reference_source_coverage_score"] = row.get("source_retrieval_score")
            row["reference_source_status"] = "missing" if missing_source else "available"
            row["failure_labels"] = [label for label in row.get("failure_labels", []) if label != "retrieval_failure"]
            if missing_source:
                row["failure_type"] = "Reference Evidence Missing"
                row["determination_state"] = "unable_to_determine"
                row["failure_labels"].append("reference_evidence_missing")
                row["failure_evidence"].pop("retrieval_failure", None)
                row["failure_evidence"]["reference_evidence_missing"] = [
                    {
                        "reason_code": "expected_source_not_in_reference_corpus",
                        "expected_source": expected_source,
                    }
                ]
                row["failure_reason_codes"] = sorted(
                    {item["reason_code"] for items in row["failure_evidence"].values() for item in items}
                )
            row["score_explanation"].update(
                {
                    "evidence_scope": "Supplied reference corpus; client retrieval not observed.",
                    "failure_labels": row["failure_labels"],
                    "failure_evidence": row["failure_evidence"],
                    "failure_reason_codes": row["failure_reason_codes"],
                }
            )
            row["automated_assessment_scope"] = "Answer quality against the supplied reference corpus; advisory only."
        else:
            row.update(
                {
                    "overall_score": None,
                    "failure_type": "Execution Error",
                    "failure_labels": ["infrastructure_failure"],
                    "failure_reason_codes": [f"imported_{response['execution_status']}"],
                    "determination_state": "unable_to_determine",
                    "safe_error": redact_pii(
                        str(response.get("safe_error") or "Client reported an unsuccessful execution.")
                    ),
                }
            )
        row.update(
            {
                "source_retrieval_score": None,
                "source_match_score": None,
                "retrieved_sources": None,
                "client_retrieval_status": "not_measured",
                "retrieval_metrics_scope": "not_measured",
                "retrieval_metrics": {"available": False, "reason": "Client retrieval was not independently observed."},
                "latency_ms": response["latency_ms"],
                "estimated_cost": response["estimated_cost"],
                "measurement_provenance": "client_reported"
                if response["latency_ms"] is not None or response["estimated_cost"] is not None
                else "not_reported",
            }
        )
        rows.append(redact_secrets(row, preserve_references=False))
    return pd.DataFrame(rows)


def apply_response_reviews(df: pd.DataFrame, reviews: list[dict[str, Any]]) -> pd.DataFrame:
    """Attach explicit decisions to exact response hashes without changing scores."""
    rows = _indexed(df.to_dict(orient="records"), "result")
    indexed = _indexed(reviews, "review")
    unknown = set(indexed) - set(rows)
    if unknown:
        raise ValueError(f"Reviews reference unknown cases: {sorted(unknown)}")
    for case_id, review in indexed.items():
        row = rows[case_id]
        for field in ("response_hash", "case_version", "knowledge_base_version"):
            if review.get(field) != row.get(field):
                raise ValueError(f"Review {field} does not match current evidence for {case_id}.")
        decision = review.get("decision")
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"Invalid review decision for {case_id}.")
        kind = review.get("reviewer_kind", "ai_assisted")
        if kind not in REVIEWER_KINDS or not str(review.get("reviewer") or "").strip():
            raise ValueError("Every review needs an explicit reviewer and reviewer_kind.")
        if not str(review.get("note") or "").strip():
            raise ValueError("Every review requires a source-based explanation or an uncertainty note.")
        execution_failed = row.get("execution_status") != "passed"
        if execution_failed != (decision == "execution_error"):
            raise ValueError(f"Execution errors must remain separate from answer quality for {case_id}.")
        reviewed_at = _timestamp(str(review.get("reviewed_at") or datetime.now(UTC).isoformat()), "reviewed_at")
        row.update(
            {
                "review_status": "reviewed",
                "review_decision": decision,
                "reviewer": str(review["reviewer"]),
                "reviewer_kind": kind,
                "review_note": str(review["note"]),
                "reviewed_at": reviewed_at,
                "review_hash": version_hash(
                    {
                        **review,
                        "reviewed_at": reviewed_at,
                        "case_version": row["case_version"],
                        "knowledge_base_version": row["knowledge_base_version"],
                    }
                ),
                "human_review_status": "human_review_declared" if kind == "human" else "ai_assisted_review_only",
            }
        )
    return pd.DataFrame(list(rows.values()))


def compare_response_reviews(baseline: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, Any]:
    """Compare only reviewed, matched cases with unchanged source/expectation versions."""
    base = _indexed(baseline.to_dict(orient="records"), "baseline")
    current = _indexed(candidate.to_dict(orient="records"), "candidate")
    if not current:
        raise ValueError("At least one candidate response is required for comparison.")
    results: list[dict[str, Any]] = []
    for case_id, row in current.items():
        previous = base.get(case_id)
        reason = None
        if previous is None:
            status, reason = "not_comparable", "No baseline response for this case."
        elif any(
            row.get(field) != previous.get(field)
            for field in ("case_version", "knowledge_base_version", "target_name", "evidence_kind")
        ):
            status, reason = (
                "not_comparable",
                "Case expectations, reference sources, target identity, or evidence kind changed.",
            )
        elif row.get("review_status") != "reviewed" or previous.get("review_status") != "reviewed":
            status, reason = "pending_review", "Both responses need an explicit source review."
        else:
            before, after = previous.get("review_decision"), row.get("review_decision")
            if "inconclusive" in {before, after}:
                status = "inconclusive"
            elif before == after:
                status = "unchanged"
            elif row.get("response_hash") == previous.get("response_hash"):
                status, reason = (
                    "review_decision_changed",
                    "The supplied response is unchanged; only its review changed.",
                )
            elif before == "failed" and after == "supported":
                status = "resolved"
            elif before == "supported" and after == "failed":
                status = "regressed"
            elif before == "execution_error":
                status = "execution_recovered"
            elif after == "execution_error":
                status = "execution_failed"
            else:
                status = "not_comparable"
        results.append(
            {
                "case_id": case_id,
                "status": status,
                "reason": reason,
                "baseline_decision": previous.get("review_decision") if previous else None,
                "candidate_decision": row.get("review_decision"),
                "baseline_response_hash": previous.get("response_hash") if previous else None,
                "candidate_response_hash": row.get("response_hash"),
            }
        )
    counts = {
        status: sum(row["status"] == status for row in results) for status in sorted({row["status"] for row in results})
    }
    report = {
        "baseline_case_count": len(base),
        "candidate_case_count": len(current),
        "compared_cases": results,
        "counts": counts,
        "scope": "Changes in explicit review decisions on supplied responses; no live performance or causal improvement claim.",
    }
    report["comparison_hash"] = version_hash(report)
    return report
