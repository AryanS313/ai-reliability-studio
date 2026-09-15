"""Plain-language display adapters; stored evidence is never modified."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from src.presentation import safe_display_text

LABELS = {
    "question": "Question",
    "expected_answer": "Expected answer",
    "actual_answer": "Assistant answer",
    "expected_source": "Expected source",
    "retrieved_sources_display": "Sources found",
    "source_name": "Source",
    "filename": "File",
    "title": "Document",
    "file_type": "File type",
    "created_at": "Saved on",
    "chunk_text": "Passage",
    "section": "Section",
    "page": "Page",
    "chunk_count": "Passages",
    "num_chunks": "Passages",
    "char_count": "Characters",
    "extraction_status": "Reading status",
    "category": "Topic",
    "severity": "Impact",
    "status": "Status",
    "run_name": "Review",
    "prompt_name": "Instructions",
    "model_name": "Model",
    "target_type": "Assistant type",
    "execution_status": "Call outcome",
    "safe_error": "What happened",
    "failure_type": "Finding",
    "suggested_fix": "Suggested next step",
    "hallucination_risk": "Unsupported-answer risk",
    "should_escalate": "Human handoff expected",
    "actual_escalation": "Human handoff observed",
    "overall_score": "Overall answer score",
    "overall_quality": "Overall answer score",
    "expected_answer_match_score": "Expected behavior match",
    "source_retrieval_score": "Expected sources found",
    "citation_correctness_score": "Citation support",
    "groundedness_score": "Answer supported by sources",
    "escalation_correctness_score": "Appropriate human handoff",
    "latency_ms": "Response time",
    "latency_p95_ms": "Slower response time (95th percentile)",
    "latency_mean_ms": "Average response time",
    "total_cost_usd": "Total recorded cost",
    "estimated_cost": "Recorded cost",
    "infrastructure_errors": "Unusable responses",
    "infrastructure_error_rate": "Unusable response rate",
    "attempt_count": "Attempts",
    "run": "Review",
    "baseline": "Earlier review",
    "candidate": "New review",
    "delta": "Change",
    "count": "Cases",
    "value": "Value",
    "metric": "Measure",
    "precision": "Flags confirmed by reviewers",
    "recall": "Reviewer findings detected",
    "f1": "Combined agreement score",
    "false_positive_rate": "Incorrect flag rate",
    "false_negative_rate": "Missed finding rate",
    "true_positive": "Correctly flagged",
    "false_positive": "Incorrectly flagged",
    "true_negative": "Correctly passed",
    "false_negative": "Missed findings",
    "sample_sufficient": "Enough reviewed cases",
    "requirements_met": "Review checks met",
    "evaluator_label": "Finding reviewed",
}
VALUES = {
    "synthetic_mock": "Fictional sample",
    "foundation_model": "Direct model",
    "external_api": "Connected assistant",
    "passed": "Completed",
    "completed": "Completed",
    "failed": "Could not complete",
    "invalid_response": "Unusable response",
    "timed_out": "Timed out",
    "rate_limited": "Provider limit reached",
    "cancelled": "Cancelled",
    "skipped": "Skipped",
    "running": "In progress",
    "pending": "Waiting",
    "Current Prompt": "Current instructions",
    "Improved Prompt": "Candidate instructions",
    "mock-model": "Fictional sample",
    "baseline": "Earlier review",
    "candidate": "New review",
}


def review_labels(value: Any) -> list[str]:
    """Normalize imported labels for native choice chips, without a JSON editor."""
    import json

    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value))
    except (ValueError, TypeError):
        return [item.strip() for item in str(value).split(",") if item.strip()]
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def field_label(name: str) -> str:
    return LABELS.get(name, name.replace("_", " ").strip().capitalize())


def display_value(value: Any, field: str = "") -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int | float):
        if field.endswith(("_score", "_rate")) or field in {"precision", "recall", "f1", "overall_quality"}:
            return f"{value:.0%}"
        if field.endswith("_ms"):
            return f"{value:,.0f} ms"
        if "cost" in field:
            return f"${value:,.4f}"
        return f"{value:g}"
    if isinstance(value, list | tuple | set):
        return "; ".join(display_value(item) for item in value) or "None recorded"
    # Display callers must select scalar fields, never serialize arbitrary dictionaries.
    if isinstance(value, dict):
        return "Supporting details retained with the report"
    text = safe_display_text(value)
    return VALUES.get(text, text) if text else "Not recorded"


def readable_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {field_label(str(key)): display_value(value, str(key)) for key, value in row.items()}
            for row in frame.to_dict("records")
        ],
        columns=[field_label(str(key)) for key in frame.columns],
    )
