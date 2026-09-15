from __future__ import annotations

import html
import json
from dataclasses import asdict
from typing import Any

import pandas as pd

from src.aggregation import LaunchGateConfig, evaluate_candidate, evaluate_candidates
from src.config import MAX_EXPORT_ROWS
from src.presentation import (
    candidate_title,
    execution_summary,
    failure_presentation,
    metric_display,
    metric_label,
    readiness_check_rows,
    safe_display_text,
    safe_nested,
)
from src.provenance import evidence_frame
from src.security import redact_pii, redact_secrets
from src.ui_display import display_value, readable_frame
from src.versioning import version_hash

REPORT_SCHEMA_VERSION = "2.1"


def json_report(df: pd.DataFrame, *, redact_personal_data: bool = True, gates: LaunchGateConfig | None = None) -> str:
    df = evidence_frame(df)
    _validate_report_size(df)
    records = _records(df, redact_personal_data)
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "metadata": report_metadata(df, gates=gates),
        "candidates": _safe_summary(evaluate_candidates(df, gates)),
        "executions": records,
    }
    payload["report_hash"] = version_hash(payload)
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def csv_report(df: pd.DataFrame, *, redact_personal_data: bool = True, gates: LaunchGateConfig | None = None) -> str:
    df = evidence_frame(df).reset_index(drop=True)
    _validate_report_size(df)
    safe = pd.DataFrame(_records(df, redact_personal_data))
    manifest = _gate_manifest(gates)
    safe["report_gate_configuration_version"] = manifest["version"]
    safe["report_gate_configuration"] = json.dumps(safe_nested(manifest["configuration"]), ensure_ascii=False)
    safe["report_candidate_verdict"] = ""
    safe["report_candidate_gate_results"] = ""
    group_columns = [
        column
        for column in ["prompt_version", "prompt_name", "model_name", "target_version", "target_type"]
        if column in df
    ]
    groups = df.groupby(group_columns, dropna=False) if group_columns else [(None, df)]
    for _, group in groups:
        evaluation = _safe_summary(evaluate_candidate(group, gates))
        safe.loc[group.index, "report_candidate_verdict"] = evaluation["verdict"]
        safe.loc[group.index, "report_candidate_gate_results"] = json.dumps(
            evaluation["gate_results"], ensure_ascii=False, default=str
        )
    for column in safe:
        safe[column] = safe[column].apply(
            lambda value: json.dumps(value, ensure_ascii=False, default=str)
            if isinstance(value, dict | list | tuple)
            else _csv_safe(value)
        )
    return safe.to_csv(index=False)


def html_report(df: pd.DataFrame, *, redact_personal_data: bool = True, gates: LaunchGateConfig | None = None) -> str:
    df = evidence_frame(df)
    _validate_report_size(df)
    candidates = _safe_summary(evaluate_candidates(df, gates))
    metadata = report_metadata(df, gates=gates)
    counts = execution_summary(df)

    def escape(value: Any) -> str:
        return html.escape(safe_display_text(value))

    def list_html(values: list[Any]) -> str:
        return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"

    def table(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<p>No measurements were recorded.</p>"
        return (
            '<div class="table-wrap">'
            + readable_frame(pd.DataFrame(rows)).to_html(index=False, escape=True, border=0)
            + "</div>"
        )

    classification = {
        "synthetic": "Fictional sample: no launch verdict",
        "mixed_synthetic_and_real": "Mixed sample and real-assistant evidence: no combined launch conclusion",
        "real_target": "Recorded responses from a real assistant",
        "unknown": "The source of these answers was not recorded",
    }[metadata["evidence_classification"]]
    count_rows = [
        {"Measure": "Distinct test cases", "Count": counts["unique_test_cases"]},
        {"Measure": "Total checks", "Count": counts["total_executions"]},
        {"Measure": "Usable answers evaluated", "Count": counts["quality_scored_executions"]},
        {"Measure": "Answers without a flagged issue", "Count": counts["quality_passes"]},
        {"Measure": "Answers needing attention", "Count": counts["quality_failures"]},
        {"Measure": "Connection or provider problems", "Count": counts["infrastructure_errors"]},
        {"Measure": "Cancelled checks", "Count": counts["cancelled_executions"]},
        {"Measure": "Skipped checks", "Count": counts["skipped_executions"]},
    ]
    candidate_sections = []
    for number, result in enumerate(candidates.values(), start=1):
        metrics = result.get("metrics", {})
        metric_rows = [
            {"Measure": metric_label(name), "Observed": metric_display(name, metrics[name])}
            for name in [
                "overall_quality",
                "groundedness",
                "citation_support",
                "escalation_accuracy",
                "execution_error_rate",
                "critical_failure_count",
                "latency_p95_ms",
                "total_cost_usd",
            ]
            if name in metrics
        ]
        interval = metrics.get("overall_quality_ci95")
        interval_text = ""
        if isinstance(interval, list | tuple) and len(interval) == 2:
            interval_text = (
                "<p>Estimated score range from the tested cases: "
                f"{escape(metric_display('overall_quality', interval[0]))} to "
                f"{escape(metric_display('overall_quality', interval[1]))}. "
                "This reflects variation among the tested cases, not the probability that the evaluator is correct.</p>"
            )
        candidate_sections.append(
            f'<section class="candidate"><h3>Evaluation {number}: {escape(candidate_title(result))}</h3>'
            f'<p class="verdict">{escape(result["verdict"])}</p>'
            "<h4>Release checks</h4>"
            + table(readiness_check_rows(result))
            + "<h4>Observed measurements</h4>"
            + table(metric_rows)
            + interval_text
            + list_html(result.get("warnings", []))
            + "</section>"
        )

    case_sections = []
    for number, row in enumerate(_records(df, redact_personal_data), start=1):
        detail = failure_presentation(row)
        status = str(row.get("execution_status") or "passed")
        usable = status in {"passed", "completed", "success"}
        expected = detail["expected_behavior"]
        actual = detail["actual_behavior"]
        title = safe_display_text(row.get("question")) or "Question not recorded"
        outcome = detail["root_cause"] if usable else display_value(status, "execution_status")
        next_action = (
            detail["recommended_action"]
            if usable
            else (
                "Repair the assistant connection or provider problem, then rerun this case. "
                "This call did not receive a quality score."
            )
        )
        sources = []
        for source in detail["source_passages"]:
            sources.append(
                f'<blockquote><p class="source">{escape(source["document"])} · {escape(source["location"])}</p>'
                f'<p class="answer">{escape(source["passage"])}</p></blockquote>'
            )
        source_html = "".join(sources) or "<p>No source passage was recorded for this check.</p>"
        reason = (
            detail["why_failed"]
            if usable
            else (
                "The assistant did not return a usable answer. Investigate the connection, credential, provider limit or response format."
            )
        )
        severity = display_value(row.get("severity"), "severity")
        case_sections.append(
            f'<article class="case"><h3>Question {number}: {escape(title)}</h3>'
            f"<p><strong>Evaluation:</strong> {escape(candidate_title(row))}</p>"
            f"<p><strong>Finding:</strong> {escape(outcome)} · <strong>Impact:</strong> {escape(severity)}</p>"
            f'<p>{escape(reason)}</p><h4>Expected behavior</h4><p class="answer">{escape(expected)}</p>'
            f'<h4>Assistant answer</h4><p class="answer">{escape(actual)}</p>'
            f"<h4>Source evidence</h4>{source_html}"
            f"<p><strong>Next step:</strong> {escape(next_action)}</p>"
            + list_html(detail["limitations"])
            + "</article>"
        )

    # Non-executable, escaped provenance preserves exact report-time policy for
    # machine verification without asking a reader to decode it in the report.
    evidence_json = (
        json.dumps(
            {"schema_version": REPORT_SCHEMA_VERSION, "metadata": metadata, "candidates": candidates},
            ensure_ascii=False,
            default=str,
        )
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Reliability Studio release review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;color:#17202a;background:#f6f8fb;line-height:1.55}}
main{{max-width:76rem;margin:auto;padding:clamp(1rem,4vw,3rem)}}
h1,h2,h3,h4{{line-height:1.25}}h2{{margin-top:2rem}}h4{{margin-bottom:.4rem}}
section,article{{background:white;border:1px solid #cbd5e1;border-radius:.5rem;padding:1rem;margin:1rem 0}}
.notice{{border-left:.3rem solid #8a5800;padding:.8rem 1rem;background:#fff8e6}}
.verdict{{font-weight:700}}.table-wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #cbd5e1;padding:.6rem;text-align:left;vertical-align:top}}th{{background:#edf2f7}}
.answer{{white-space:pre-wrap;overflow-wrap:anywhere}}blockquote{{margin:1rem 0;padding-left:1rem;border-left:.25rem solid #718096}}
.source{{font-weight:600}}li{{margin:.3rem 0}}@media print{{body{{background:white}}main{{max-width:none;padding:0}}section,article{{break-inside:avoid}}}}
</style></head><body><main>
<h1>Your release review</h1><p class="notice">{escape(classification)}</p>
<p>Use this report to decide what to inspect and change next. A human owns the release decision.
Automated scores summarize checks on these cases; they are not a safety certification or a measured chance of correctness.</p>
<h2>What was checked</h2>{table(count_rows)}
<p>Unusable calls are excluded from answer-quality averages and still count against execution requirements.</p>
<h2>Candidate verdicts</h2>{''.join(candidate_sections) or '<p>No candidate evidence was recorded.</p>'}
<h2>Evidence limits</h2>{list_html(metadata['limitations'])}
<h2>Question-by-question evidence</h2>{''.join(case_sections) or '<p>No checks were recorded.</p>'}
<footer><p>Detected personal data and secrets are redacted. Review this report before sharing: automated redaction cannot identify every confidential detail.
Use the technical JSON or CSV export when an engineer needs the complete evidence record and exact version identifiers.</p></footer>
<script type="application/json" id="report-evidence">{evidence_json}</script>
</main></body></html>"""


def report_metadata(df: pd.DataFrame, *, gates: LaunchGateConfig | None = None) -> dict[str, Any]:
    df = evidence_frame(df)
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
    if "external_api" in target_types:
        limitations.append(
            "Retrieval scores measure Studio's local reference retrieval. The connected assistant's internal retrieval is not observed by this adapter."
        )
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
        "report_gate_manifest": _gate_manifest(gates),
        "timestamps": _unique(df, "run_timestamp") or _unique(df, "created_at") or _unique(df, "timestamp"),
        "environments": _unique(df, "environment"),
        "execution_counts": {key: value for key, value in counts.items() if key != "message"},
        "evidence_classification": evidence_classification,
        "calibration_status": calibration_statuses,
        "human_review_status": human_review_statuses,
        "retrieval_metrics_scope": _unique(df, "retrieval_metrics_scope") or ["not_recorded"],
        "client_retrieval_status": _unique(df, "client_retrieval_status") or ["not_recorded"],
        "limitations": limitations,
    }
    return safe_nested(metadata)


def _gate_manifest(gates: LaunchGateConfig | None) -> dict[str, Any]:
    configuration = asdict(gates or LaunchGateConfig())
    return {
        "configuration": configuration,
        "version": version_hash(configuration),
        "scope": "Report-time launch assessment; original run and scoring provenance are preserved.",
    }


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
        return {redact_pii(str(key)): _redact_nested_pii(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_nested_pii(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_nested_pii(item) for item in value)
    return redact_pii(str(value)) if isinstance(value, str) else value


def _safe_summary(value: Any) -> Any:
    """Summary labels may contain user content too, including mapping keys."""
    if isinstance(value, dict):
        return {str(safe_nested(str(key))): _safe_summary(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_summary(item) for item in value]
    return safe_nested(value)


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
