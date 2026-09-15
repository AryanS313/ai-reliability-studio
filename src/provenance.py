"""Restore result evidence persisted in metadata by schema-compatible repositories."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

PROVENANCE_FIELDS = (
    "expected_behavior",
    "expected_answers",
    "expected_sources",
    "expected_escalation_destination",
    "expected_escalation_urgency",
    "run_id",
    "run_timestamp",
    "environment",
    "manifest_hash",
    "dataset_version",
    "knowledge_base_version",
    "retrieval_configuration_version",
    "evaluation_configuration_version",
    "attempt_count",
    "cache_hit",
    "execution_key",
    "provider",
    "response_reported_model",
    "model_identity_provenance",
    "retrieval_metrics_scope",
    "client_retrieval_status",
)


def evidence_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Hydrate only the allowlisted evidence fields; never overwrite stored values."""
    if frame.empty:
        return frame.copy()
    records: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        metadata = record.get("metadata") or record.get("metadata_json") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (ValueError, TypeError):
                metadata = {}
        provenance = metadata.get("provenance", {}) if isinstance(metadata, dict) else {}
        if isinstance(provenance, dict):
            for field in PROVENANCE_FIELDS:
                current = record.get(field)
                if field in provenance and (current is None or (isinstance(current, float) and pd.isna(current))):
                    record[field] = provenance[field]
        records.append(record)
    return pd.DataFrame(records, index=frame.index)
