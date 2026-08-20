from __future__ import annotations

import html
import json
from typing import Any

import pandas as pd

from src.aggregation import evaluate_candidates
from src.config import MAX_EXPORT_ROWS
from src.presentation import execution_summary, safe_nested
from src.security import redact_pii, redact_secrets
from src.versioning import version_hash

REPORT_SCHEMA_VERSION = "2.0"


def json_report(df: pd.DataFrame, *, redact_personal_data: bool = True) -> str:
    _validate_report_size(df)
    records = _records(df, redact_personal_data)
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "metadata": report_metadata(df),
        "candidates": safe_nested(evaluate_candidates(df)),
        "executions": records,
    }
    payload["report_hash"] = version_hash(payload)
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def csv_report(df: pd.DataFrame, *, redact_personal_data: bool = True) -> str:
    _validate_report_size(df)
    safe = pd.DataFrame(_records(df, redact_personal_data))
    for column in safe:
        safe[column] = safe[column].apply(
            lambda value: json.dumps(value, ensure_ascii=False, default=str)
            if isinstance(value, dict | list | tuple)
            else _csv_safe(value)
        )
    return safe.to_csv(index=False)


def html_report(df: pd.DataFrame, *, redact_personal_data: bool = True) -> str:
    _validate_report_size(df)
    candidates = evaluate_candidates(df)
    metadata = report_metadata(df)
    summary_rows = []
    for name, result in candidates.items():
        summary_rows.append(
            f"<tr><td>{html.escape(name)}</td><td>{html.escape(str(result['verdict']))}</td>"
            f"<td>{html.escape(json.dumps(result.get('metrics', {}), default=str))}</td></tr>"
        )
    execution_table = pd.DataFrame(_records(df, redact_personal_data)).to_html(index=False, escape=True)
    metadata_table = pd.DataFrame(
        [{"field": key, "value": json.dumps(value, ensure_ascii=False, default=str)} for key, value in metadata.items()]
    ).to_html(index=False, escape=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>AI Reliability Studio report</title>
<style>body{{font-family:system-ui;margin:2rem;color:#17202a}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #dfe5ee;padding:.45rem;text-align:left;vertical-align:top}}th{{background:#f5f7fa}}</style></head>
<body><h1>AI Reliability Studio report</h1>
<p>Quality metrics exclude infrastructure failures. Synthetic runs cannot establish launch readiness.</p>
<h2>Evidence and provenance</h2>{metadata_table}
<h2>Candidate verdicts</h2><table><thead><tr><th>Candidate</th><th>Verdict</th><th>Metrics</th></tr></thead>
<tbody>{''.join(summary_rows)}</tbody></table><h2>Executions</h2>{execution_table}</body></html>"""


def report_metadata(df: pd.DataFrame) -> dict[str, Any]:
    counts = execution_summary(df)
    target_types = _unique(df, "target_type")
    if target_types == ["synthetic_mock"]:
        evidence_classification = "synthetic"
    elif "synthetic_mock" in target_types:
        evidence_classification = "mixed_synthetic_and_real"
    else:
        evidence_classification = "real_target" if target_types else "unknown"
    calibration_statuses = _unique(df, "calibration_status") or ["not_recorded"]
    human_review_statuses = _unique(df, "human_review_status") or ["not_recorded"]
    limitations = [
        "Automated scores are estimates and do not replace expert review of high-severity cases.",
        "Infrastructure failures are excluded from quality averages and reported separately.",
    ]
    if evidence_classification != "real_target":
        limitations.append("Synthetic evidence demonstrates workflow and cannot establish production launch readiness.")
    if calibration_statuses != ["calibrated"]:
        limitations.append("A qualifying held-out human calibration was not recorded for all evidence.")
    metadata = {
        "run_ids": _unique(df, "run_id"),
        "candidate_ids": _unique(df, "candidate_id"),
        "prompt_versions": _unique(df, "prompt_version"),
        "target_versions": _unique(df, "target_version"),
        "target_types": target_types,
        "models": _unique(df, "model_name"),
        "providers": _unique(df, "provider"),
        "dataset_versions": _unique(df, "dataset_version"),
        "knowledge_base_versions": _unique(df, "knowledge_base_version") or _unique(df, "document_version"),
        "evaluator_versions": _unique(df, "evaluator_version"),
        "threshold_versions": _unique(df, "threshold_version"),
        "gate_configuration_versions": _unique(df, "gate_configuration_version"),
        "timestamps": _unique(df, "run_timestamp") or _unique(df, "created_at") or _unique(df, "timestamp"),
        "environments": _unique(df, "environment"),
        "execution_counts": {key: value for key, value in counts.items() if key != "message"},
        "evidence_classification": evidence_classification,
        "calibration_status": calibration_statuses,
        "human_review_status": human_review_statuses,
        "limitations": limitations,
    }
    return safe_nested(metadata)


def _records(df: pd.DataFrame, redact_personal_data: bool) -> list[dict[str, Any]]:
    records = df.where(pd.notna(df), None).to_dict(orient="records")
    safe_records = []
    for record in records:
        safe = redact_secrets(record, preserve_references=False)
        if redact_personal_data:
            safe = _redact_nested_pii(safe)
        safe_records.append(safe)
    return safe_records


def _redact_nested_pii(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_nested_pii(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_nested_pii(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_nested_pii(item) for item in value)
    return redact_pii(str(value)) if isinstance(value, str) else value


def _unique(df: pd.DataFrame, column: str) -> list[str]:
    if df.empty or column not in df:
        return []
    return sorted({str(value) for value in df[column].dropna() if str(value).strip()})


def _csv_safe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _validate_report_size(df: pd.DataFrame) -> None:
    if len(df) > MAX_EXPORT_ROWS:
        raise ValueError(
            f"This export contains {len(df)} rows; the configured safe limit is {MAX_EXPORT_ROWS}. "
            "Filter by run or use a production streaming export adapter."
        )
