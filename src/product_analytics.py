"""Payload-free product events stored in the authorized workspace's audit log.

No network exporter, cookies, fingerprints, names, URLs or free-text properties.
The enclosing audit record still has workspace/user authorization metadata; these
are local operational records, not a claim of anonymous hosted analytics.
"""

from __future__ import annotations

import math
import re
from typing import Any

from src.domain import WorkspaceContext
from src.storage import Repository

EVENTS = frozenset(
    {
        "session_started",
        "project_created",
        "project_reopened",
        "sample_loaded",
        "document_ingested",
        "dataset_saved",
        "target_configured",
        "target_health_checked",
        "run_started",
        "run_completed",
        "report_viewed",
        "comparison_viewed",
        "report_exported",
        "workflow_error",
        "decision_recorded",
    }
)
ENUMS = {
    "mode": {"public-demo", "hosted-session", "local", "authenticated", "browser"},
    "target_type": {"synthetic_mock", "foundation_model", "external_api"},
    "outcome": {"success", "partial", "failure", "inconclusive"},
    "stage": {"project", "documents", "dataset", "target", "run", "review", "export"},
    "format": {"csv", "json", "html"},
    "decision": {"hold", "investigate", "internal_test", "controlled_beta"},
    "next_action": {"fix_prompt", "fix_sources", "fix_target", "add_cases", "human_review", "rerun"},
}
COUNTS = frozenset(
    {
        "project_id",
        "run_id",
        "case_count",
        "execution_count",
        "scored_count",
        "error_count",
        "document_count",
        "chunk_count",
        "action_count",
    }
)
BOOLEANS = frozenset({"synthetic", "ranking_supported"})


def validate_event(name: str, session_id: str, properties: dict[str, Any]) -> dict[str, Any]:
    """Reject rather than silently persist any unrecognized or content-like value."""
    if name not in EVENTS or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        raise ValueError("Unknown product event or invalid random session identifier.")
    # This random product journey reference is not an authentication session ID.
    # Keep credential-like session_id fields redacted by the generic audit sink.
    cleaned: dict[str, Any] = {"schema_version": 1, "journey_id": session_id}
    for key, value in properties.items():
        if key in ENUMS:
            valid = isinstance(value, str) and value in ENUMS[key]
        elif key in COUNTS:
            valid = type(value) is int and 0 <= value <= 10_000_000
        elif key in BOOLEANS:
            valid = type(value) is bool
        elif key == "duration_ms":
            valid = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 86_400_000
        else:
            valid = False
        if not valid:
            raise ValueError(f"Invalid product event property: {key}.")
        cleaned[key] = value
    return cleaned


def record_event(
    repository: Repository, context: WorkspaceContext, name: str, session_id: str, **properties: Any
) -> None:
    cleaned = validate_event(name, session_id, properties)
    repository.audit(context, "product." + name, "product_event", None, cleaned)
