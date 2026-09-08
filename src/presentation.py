from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pandas as pd

from src.security import redact_pii, redact_secrets
from src.suggestions import suggestion_for_failure

SUCCESS_STATUSES = {"passed", "completed", "success"}


def retry_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Separate observed retries from unknown historical or imported attempt counts."""
    attempts = pd.to_numeric(df.get("attempt_count", pd.Series(index=df.index, dtype=float)), errors="coerce")
    known = attempts.notna() & attempts.ge(0) & attempts.mod(1).eq(0)
    observed = int(attempts[known].sub(1).clip(lower=0).sum())
    return {
        "retries": observed if known.all() else None,
        "observed_retries": observed,
        "attempt_counts_recorded": int(known.sum()),
        "attempt_counts_unknown": int((~known).sum()),
    }


def execution_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Return consistent run counts and context-sensitive completion wording."""
    if df.empty:
        return {
            "unique_test_cases": 0,
            "total_executions": 0,
            "quality_scored_executions": 0,
            "quality_passes": 0,
            "quality_failures": 0,
            "infrastructure_errors": 0,
            "cancelled_executions": 0,
            "skipped_executions": 0,
            "retries": 0,
            "message": "Run complete: no executions were created.",
        }
    statuses = df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)).fillna("").astype(str)
    quality_mask = statuses.isin(SUCCESS_STATUSES)
    failure_types = df.get("failure_type", pd.Series(["Passed"] * len(df), index=df.index)).fillna("").astype(str)
    quality_passes = int((quality_mask & failure_types.eq("Passed")).sum())
    quality_failures = int((quality_mask & ~failure_types.eq("Passed")).sum())
    cancelled = int(statuses.eq("cancelled").sum())
    skipped = int(statuses.eq("skipped").sum())
    infrastructure = int((~quality_mask & ~statuses.isin({"cancelled", "skipped"})).sum())
    retry_counts = retry_summary(df)
    retries = retry_counts["retries"]
    unique_column = "case_id" if "case_id" in df else "question"
    counts: dict[str, Any] = {
        "unique_test_cases": int(df[unique_column].nunique()) if unique_column in df else len(df),
        "total_executions": len(df),
        "quality_scored_executions": int(quality_mask.sum()),
        "quality_passes": quality_passes,
        "quality_failures": quality_failures,
        "infrastructure_errors": infrastructure,
        "cancelled_executions": cancelled,
        "skipped_executions": skipped,
        **retry_counts,
    }
    parts = [f"Run complete: {len(df)} total executions"]
    if quality_mask.all():
        parts.append("all target calls completed")
    else:
        parts.append(f"{int(quality_mask.sum())} were quality-scored")
    parts.append(f"{quality_passes} quality passes")
    parts.append(f"{quality_failures} quality failures")
    if infrastructure:
        parts.append(f"{infrastructure} infrastructure errors were excluded from quality scoring")
    if cancelled:
        parts.append(f"{cancelled} cancelled")
    if skipped:
        parts.append(f"{skipped} skipped")
    if retries:
        parts.append(f"{retries} retries")
    elif retries is None:
        parts.append("retry totals were not recorded for every execution")
    counts["message"] = "; ".join(parts) + "."
    return counts


def failure_presentation(row: Mapping[str, Any]) -> dict[str, Any]:
    failure_type = str(row.get("failure_type") or "Evaluation failure")
    labels = _as_list(row.get("failure_labels"))
    reason_codes = _as_list(row.get("failure_reason_codes"))
    evidence = _jsonish(row.get("failure_evidence"))
    score_explanation = _jsonish(row.get("score_explanation"))
    expected = safe_display_text(row.get("expected_answer") or row.get("expected_behavior"))
    actual = safe_display_text(row.get("actual_answer"))
    confidence = _number(row.get("evaluator_confidence"))
    calibration = str(row.get("calibration_status") or "not_recorded")
    root_cause = failure_type if failure_type != "Passed" else "No quality failure"
    reason = _why_failed(failure_type, labels, reason_codes, score_explanation)
    limitations = _limitations(confidence, calibration, row)
    sources = []
    for chunk in _as_list_of_dicts(row.get("retrieved_chunks")):
        sources.append(
            {
                "document": safe_display_text(chunk.get("source_name") or chunk.get("document_id") or "Unknown source"),
                "location": safe_display_text(
                    chunk.get("page") or chunk.get("section") or chunk.get("chunk_id") or "Location not recorded"
                ),
                "passage": safe_display_text(chunk.get("chunk_text") or chunk.get("text") or ""),
                "similarity": _number(chunk.get("similarity")),
            }
        )
    return {
        "summary": f"{root_cause} on case {safe_display_text(row.get('case_id') or 'unknown')}.",
        "root_cause": root_cause,
        "why_failed": reason,
        "expected_behavior": expected or "No reference behavior was recorded.",
        "actual_behavior": actual or "No answer was returned.",
        "source_passages": sources,
        "confidence": confidence,
        "limitations": limitations,
        "recommended_action": suggestion_for_failure(failure_type),
        "raw_evaluator_output": safe_nested({"failure_evidence": evidence, "score_explanation": score_explanation}),
        "final_prompt": safe_display_text(row.get("final_prompt")),
        "technical_metadata": safe_nested(
            {
                key: row.get(key)
                for key in [
                    "run_id",
                    "case_id",
                    "candidate_id",
                    "prompt_version",
                    "target_version",
                    "target_type",
                    "model_name",
                    "evaluator_version",
                    "threshold_version",
                    "calibration_version",
                    "execution_status",
                    "error_code",
                ]
                if key in row
            }
        ),
    }


def safe_display_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return redact_pii(str(redact_secrets(str(value), preserve_references=False)))


def safe_nested(value: Any) -> Any:
    redacted = redact_secrets(value, preserve_references=False)
    if isinstance(redacted, dict):
        return {str(key): safe_nested(item) for key, item in redacted.items()}
    if isinstance(redacted, list):
        return [safe_nested(item) for item in redacted]
    if isinstance(redacted, tuple):
        return tuple(safe_nested(item) for item in redacted)
    return redact_pii(redacted) if isinstance(redacted, str) else redacted


def _why_failed(
    failure_type: str,
    labels: list[str],
    reason_codes: list[str],
    score_explanation: Any,
) -> str:
    details = []
    if labels:
        details.append("Labels: " + ", ".join(label.replace("_", " ") for label in labels))
    if reason_codes:
        details.append("Reason codes: " + ", ".join(reason_codes))
    if isinstance(score_explanation, dict):
        relationship = score_explanation.get("answer_relationship")
        if isinstance(relationship, dict) and relationship.get("classification"):
            details.append(f"Answer relationship: {relationship['classification']}")
    return ". ".join(details) + ("." if details else f"The evaluator classified this as {failure_type}.")


def _limitations(confidence: float | None, calibration: str, row: Mapping[str, Any]) -> list[str]:
    limitations = []
    if confidence is None:
        limitations.append("Evaluator confidence was not recorded; human review is recommended.")
    elif confidence < 0.7:
        limitations.append("Evaluator confidence is low; treat this result as a review candidate.")
    if calibration != "calibrated":
        limitations.append("This evaluator was not linked to a qualifying held-out human calibration.")
    if str(row.get("target_type") or "") == "synthetic_mock":
        limitations.append("Synthetic evidence demonstrates workflow only and cannot establish model quality.")
    return limitations or ["Automated evaluation remains an estimate; inspect the cited evidence before acting."]


def _jsonish(value: Any) -> Any:
    if isinstance(value, dict | list | tuple):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    try:
        return json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return {"value": safe_display_text(value)}


def _as_list(value: Any) -> list[str]:
    parsed = _jsonish(value)
    if isinstance(parsed, list | tuple):
        return [safe_display_text(item) for item in parsed]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    parsed = _jsonish(value)
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list | tuple) else []


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return None if pd.isna(number) else number
    except (TypeError, ValueError):
        return None
