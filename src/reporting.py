from __future__ import annotations

import html
import json
import math
from dataclasses import asdict, replace
from numbers import Real
from typing import Any

import pandas as pd

from src.aggregation import LaunchGateConfig, evaluate_candidates
from src.config import MAX_EXPORT_ROWS
from src.document_loader import source_extraction_warnings
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
LOCAL_RETRIEVAL_SCOPE = "evaluator_local_reference_retrieval"
RETRIEVAL_NOTICE = (
    "source_retrieval_score and retrieval_metrics measure Studio's local reference retrieval. "
    "They do not measure the client's retriever. Client retrieval remains unmeasured unless an authentic "
    "target trace is explicitly mapped and evaluated in separate client retrieval fields."
)


def validate_launch_gates(gates: LaunchGateConfig | None = None) -> LaunchGateConfig:
    """Validate configuration before a run or export; normalize mutable JSON arrays."""
    gates = LaunchGateConfig() if gates is None else gates
    if not isinstance(gates, LaunchGateConfig):
        raise ValueError("Launch gates must be a LaunchGateConfig.")
    rates = (
        "minimum_overall_quality",
        "minimum_groundedness",
        "minimum_citation_support",
        "minimum_escalation_accuracy",
        "maximum_unsupported_claim_rate",
        "maximum_execution_error_rate",
    )
    for name in rates:
        value = getattr(gates, name)
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(value)
            or not 0 <= float(value) <= 1
        ):
            raise ValueError(f"{name} must be a finite number between 0 and 1.")
    for name, minimum in (("minimum_sample_size", 1), ("maximum_severe_safety_failures", 0)):
        value = getattr(gates, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer of at least {minimum}.")
    for name in ("maximum_latency_p95_ms", "maximum_cost_usd"):
        value = getattr(gates, name)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value < 0
        ):
            raise ValueError(f"{name} must be null or a finite nonnegative number.")
    if not isinstance(gates.require_calibration, bool):
        raise ValueError("require_calibration must be a boolean.")
    normalized = {}
    for name in ("required_categories", "critical_labels"):
        value = getattr(gates, name)
        if not isinstance(value, tuple | list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError(f"{name} must be an array of nonempty strings.")
        normalized[name] = tuple(value)
    return replace(
        gates, required_categories=normalized["required_categories"], critical_labels=normalized["critical_labels"]
    )


def build_report_payload(
    df: pd.DataFrame,
    *,
    gates: LaunchGateConfig | None = None,
    redact_personal_data: bool = True,
) -> dict[str, Any]:
    """Create one detached, hashed report snapshot used by rendering and the CLI exit decision."""
    _validate_report_size(df)
    df = _hydrate_model_identity(evidence_frame(df))
    gates = validate_launch_gates(gates)
    records = df.where(pd.notna(df), None).to_dict(orient="records")
    for record in records:
        # Old runs lacked this attribution; the historical metrics are local too.
        record.setdefault("retrieval_metrics_scope", LOCAL_RETRIEVAL_SCOPE)
        record.setdefault("client_retrieval_status", "not_measured")
        record.setdefault("human_review_status", "not_recorded")
        record["automatic_outcome"] = _automatic_outcome(record)
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "metadata": report_metadata(df, gates=gates),
        "gate_configuration": asdict(gates),
        "gate_configuration_version": version_hash(asdict(gates)),
        "candidates": evaluate_candidates(df, gates),
        "review_summary": _review_summary(records),
        "automatic_outcomes": _automatic_outcome_counts(records),
        "run_manifests": _run_manifests(df, redact_personal_data),
        "executions": records,
    }
    group_columns = [
        column
        for column in ["prompt_version", "prompt_name", "model_name", "target_version", "target_type"]
        if column in df
    ]
    groups = (
        df.reset_index(drop=True).groupby(group_columns, dropna=False)
        if group_columns
        else [(None, df.reset_index(drop=True))]
        if not df.empty
        else []
    )
    for (_, group), evaluation in zip(groups, payload["candidates"].values(), strict=True):
        for index in group.index:
            records[index]["report_candidate_verdict"] = evaluation["verdict"]
            records[index]["report_candidate_gate_results"] = evaluation["gate_results"]
    # Candidate names are user labels, not credential field names. Redact each
    # label as content and each assessment as a structure so a name mentioning
    # a secret cannot erase the verdict or its gate evidence.
    candidates = {
        str(_safe_export(name, redact_personal_data)): _safe_export(assessment, redact_personal_data)
        for name, assessment in payload["candidates"].items()
    }
    payload["candidates"] = {}
    payload = _safe_export(payload, redact_personal_data)
    payload["candidates"] = candidates
    payload["report_hash"] = version_hash(payload)
    return payload


def render_report_payload(payload: dict[str, Any], *, format: str = "json") -> str:
    """Render the same detached snapshot used by CLI gates, without re-evaluating it."""
    if format == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False, default=str, allow_nan=False)
    if format == "csv":
        return _csv_payload(payload)
    if format == "html":
        return _html_payload(payload)
    raise ValueError(f"Unsupported report format: {format}")


def json_report(df: pd.DataFrame, *, gates: LaunchGateConfig | None = None, redact_personal_data: bool = True) -> str:
    return render_report_payload(build_report_payload(df, gates=gates, redact_personal_data=redact_personal_data))


def csv_report(df: pd.DataFrame, *, gates: LaunchGateConfig | None = None, redact_personal_data: bool = True) -> str:
    return render_report_payload(
        build_report_payload(df, gates=gates, redact_personal_data=redact_personal_data), format="csv"
    )


def html_report(df: pd.DataFrame, *, gates: LaunchGateConfig | None = None, redact_personal_data: bool = True) -> str:
    return render_report_payload(
        build_report_payload(df, gates=gates, redact_personal_data=redact_personal_data), format="html"
    )


def report_metadata(df: pd.DataFrame, *, gates: LaunchGateConfig | None = None) -> dict[str, Any]:
    df = _hydrate_model_identity(evidence_frame(df))
    gates = validate_launch_gates(gates)
    counts = execution_summary(df)
    target_types = _unique(df, "target_type")
    if target_types == ["synthetic_mock"]:
        evidence_classification = "synthetic"
    elif "synthetic_mock" in target_types:
        evidence_classification = "mixed_synthetic_and_real"
    elif "saved_responses" in target_types:
        evidence_kinds = _unique(df, "evidence_kind", missing="unknown")
        if target_types != ["saved_responses"]:
            evidence_classification = "mixed_live_and_imported_responses"
        elif evidence_kinds == ["fixture"]:
            evidence_classification = "synthetic_fixture"
        elif evidence_kinds == ["client_supplied"]:
            evidence_classification = "client_supplied_responses"
        else:
            evidence_classification = "mixed_or_unknown_imported_responses"
    else:
        evidence_classification = (
            "real_target" if target_types and set(target_types) <= {"foundation_model", "external_api"} else "unknown"
        )
    calibration_statuses = _unique(df, "calibration_status", missing="not_recorded") or ["not_recorded"]
    human_review_statuses = _unique(df, "human_review_status", missing="not_recorded") or ["not_recorded"]
    manifests = _manifest_values(df)
    source_versions = set(_flattened_unique(df, "document_versions") or _unique(df, "document_version"))
    for manifest in manifests:
        source_versions.update(
            str(document["version"]) for document in manifest.get("documents", []) if document.get("version")
        )
    limitations = [
        "Automated scores are estimates and do not replace expert review of high-severity cases.",
        "Infrastructure failures are excluded from quality averages and reported separately.",
        "Reported costs describe the returned answers, not a provider invoice. Charges for failed attempts and other activity may be unknown.",
        RETRIEVAL_NOTICE,
        "Manifest hashes provide content integrity, not independent proof of execution, review, or source authenticity.",
    ]
    if "synthetic_mock" in target_types or "fixture" in _unique(df, "evidence_kind"):
        limitations.append("Synthetic evidence demonstrates workflow and cannot establish production launch readiness.")
    if "saved_responses" in target_types:
        limitations.append(
            "Imported responses are supplied artifacts; their origin is not independently verified, and offline review provides no launch verdict."
        )
    extraction_notices = source_extraction_warnings(
        [
            chunk
            for manifest in manifests
            for chunk in (manifest.get("reference_chunks") or [])
            if isinstance(chunk, dict)
        ]
        + [
            {"extraction_warnings": document.get("extraction_notices", [])}
            for manifest in manifests
            for document in (manifest.get("documents") or [])
            if isinstance(document, dict)
        ]
    )
    if extraction_notices:
        limitations.append(
            "Some reference documents have extraction notices. Check the original documents before treating "
            "the imported passages as complete: " + " ".join(extraction_notices)
        )
    if calibration_statuses != ["calibrated"]:
        limitations.append("A qualifying held-out human calibration was not recorded for all evidence.")
    if not gates.require_calibration:
        limitations.append(
            "The report gate configuration explicitly disables the calibration requirement; this does not establish calibration."
        )
    if len(manifests) == 0:
        limitations.append(
            "No immutable run manifest was supplied with these rows; missing provenance remains unknown."
        )
    metadata = {
        "run_ids": _unique(df, "run_id"),
        "candidate_ids": _unique(df, "candidate_id"),
        "prompt_versions": _unique(df, "prompt_version"),
        "target_versions": _unique(df, "target_version"),
        "target_types": target_types,
        "models": _unique(df, "model_name"),
        "providers": _unique(df, "provider")
        if "model_identity_provenance" in df
        else _unique(df, "provider") or _manifest_nested_values(manifests, "model", "provider"),
        "model_identity_provenance": _unique(df, "model_identity_provenance", missing="not_recorded"),
        "dataset_versions": _unique(df, "dataset_version")
        or _manifest_nested_values(manifests, "dataset", "content_hash"),
        "document_versions": sorted(source_versions),
        "knowledge_base_versions": _unique(df, "knowledge_base_version"),
        "source_extraction_notices": extraction_notices,
        "evaluator_versions": _unique(df, "evaluator_version"),
        "threshold_versions": _unique(df, "threshold_version"),
        "gate_configuration_versions": [version_hash(asdict(gates))],
        "report_gate_manifest": _gate_manifest(gates),
        "recorded_run_gate_configuration_versions": _unique(df, "gate_configuration_version"),
        "timestamps": _unique(df, "run_timestamp")
        or _unique(df, "created_at")
        or _unique(df, "timestamp")
        or sorted({str(manifest["created_at"]) for manifest in manifests if manifest.get("created_at")}),
        "environments": _unique(df, "environment")
        or sorted({str(manifest["environment"]) for manifest in manifests if manifest.get("environment")}),
        "execution_counts": {key: value for key, value in counts.items() if key != "message"},
        "execution_count_scope": "Automatic assessment legacy pass/nonpass counts; quality_failures includes unresolved assessments. Use automatic_outcomes for separated counts and review_summary for reviewed decisions.",
        "evidence_classification": evidence_classification,
        "calibration_status": calibration_statuses,
        "human_review_status": human_review_statuses,
        "retrieval_metrics_scope": _unique(df, "retrieval_metrics_scope", missing=LOCAL_RETRIEVAL_SCOPE),
        "client_retrieval_status": _unique(df, "client_retrieval_status", missing="not_measured"),
        "limitations": limitations,
    }
    return safe_nested(metadata)


def _hydrate_model_identity(df: pd.DataFrame) -> pd.DataFrame:
    """Recover observed identity from persisted metadata without using runner defaults."""
    if df.empty or not ({"metadata", "metadata_json"} & set(df.columns)):
        return df
    records = df.to_dict(orient="records")
    changed = False
    for row in records:
        metadata = _parse_manifest(row.get("metadata")) or _parse_manifest(row.get("metadata_json"))
        identity = metadata.get("model_identity")
        if not isinstance(identity, dict) or identity.get("provenance") not in {"target_response", "not_reported"}:
            continue
        provider = identity.get("reported_provider")
        model = identity.get("reported_model")
        row.update(
            {
                "provider": provider if isinstance(provider, str) and provider.strip() else None,
                "model_name": model if isinstance(model, str) and model.strip() else None,
                "response_reported_provider": provider if isinstance(provider, str) and provider.strip() else None,
                "response_reported_model": model if isinstance(model, str) and model.strip() else None,
                "configured_runner_provider": identity.get("configured_runner_provider"),
                "configured_runner_model": identity.get("configured_runner_model"),
                "model_identity_provenance": identity["provenance"],
            }
        )
        changed = True
    return pd.DataFrame(records, index=df.index) if changed else df


def _automatic_outcome(row: dict[str, Any]) -> str:
    status = row.get("execution_status", "passed")
    if status in {"cancelled", "skipped"}:
        return str(status)
    if status not in {"passed", "completed", "success"}:
        return "execution_error"
    if row.get("determination_state") == "unable_to_determine":
        return "unresolved"
    primary = row.get("failure_type")
    if primary in {None, "", "Needs Review", "Reference Evidence Missing", "Not Scored"}:
        return "unresolved"
    return "passed" if primary == "Passed" else "failed"


def _automatic_outcome_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = [_automatic_outcome(row) for row in records]
    return {
        "total_responses": len(records),
        **{
            key: outcomes.count(key)
            for key in ("passed", "failed", "unresolved", "execution_error", "cancelled", "skipped")
        },
        "scope": "Terminal automatic determination, not reviewed facts; unable_to_determine always abstains, and raw classifier labels remain advisory flags.",
    }


_REVIEW_DECISIONS = ("supported", "failed", "inconclusive", "execution_error")


def _review_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    applicable = any(row.get("target_type") == "saved_responses" or "review_status" in row for row in records)
    reviewed = [
        row
        for row in records
        if row.get("review_status") == "reviewed" and row.get("review_decision") in _REVIEW_DECISIONS
    ]
    kinds = sorted({str(row.get("reviewer_kind") or "not_recorded") for row in reviewed})
    return {
        "applicable": applicable,
        "total_responses": len(records),
        "reviewed_responses": len(reviewed),
        "pending_responses": len(records) - len(reviewed),
        "decisions": {
            decision: sum(row.get("review_decision") == decision for row in reviewed) for decision in _REVIEW_DECISIONS
        },
        "reviewer_kinds": {
            kind: sum(str(row.get("reviewer_kind") or "not_recorded") == kind for row in reviewed) for kind in kinds
        },
        "scope": "Declared source review decisions; reviewer identities and human participation are not independently attested.",
    }


def _evidence_banner_html(payload: dict[str, Any]) -> str:
    classification = payload["metadata"].get("evidence_classification", "unknown")
    labels = {
        "synthetic_fixture": "Fictional workflow rehearsal — no real assistant or customer evidence.",
        "synthetic": "Synthetic demonstration — no real assistant or customer evidence.",
        "client_supplied_responses": "Client-supplied responses — origin and live execution are not independently verified.",
        "mixed_synthetic_and_real": "Mixed synthetic and target evidence — synthetic examples do not establish live performance.",
        "mixed_or_unknown_imported_responses": "Mixed or unknown supplied evidence — inspect each response's evidence kind before interpreting findings.",
        "mixed_live_and_imported_responses": "Mixed target executions and supplied responses — their evidence origins differ.",
        "real_target": "Target execution report — automated results require source review.",
        "unknown": "Evidence origin is not recorded.",
    }
    label = labels.get(classification, "Evidence origin is not recorded.")
    return f"<aside class='review-summary' aria-label='Evidence classification'><strong>{html.escape(label)}</strong></aside>"


def _review_html(payload: dict[str, Any]) -> str:
    summary = payload.get("review_summary", {})
    if not summary.get("applicable"):
        return ""
    count_text = (
        f"{summary['reviewed_responses']} of {summary['total_responses']} responses reviewed; "
        f"{summary['pending_responses']} pending review."
    )
    decisions = summary["decisions"]
    decisions_text = (
        f"Reviewed decisions: {decisions['supported']} supported; {decisions['failed']} failed; "
        f"{decisions['inconclusive']} inconclusive; {decisions['execution_error']} execution errors."
    )
    kinds = summary["reviewer_kinds"]
    participation = (
        f"Review participation: {kinds.get('ai_assisted', 0)} AI-assisted; "
        f"{kinds.get('human', 0)} declared human; {kinds.get('not_recorded', 0)} not recorded."
    )
    cases = []
    for row in payload["executions"]:
        complete = row.get("review_status") == "reviewed" and row.get("review_decision") in _REVIEW_DECISIONS
        decision = str(row.get("review_decision")) if complete else "pending"
        label = decision.replace("_", " ").capitalize() if complete else "Pending review"
        detail = failure_presentation(
            {**row, "retrieved_chunks": row.get("reference_chunks") or row.get("retrieved_chunks") or []}
        )
        question = html.escape(str(row.get("question") or "Question not recorded"))
        answer = html.escape(str(row.get("actual_answer") or "No answer recorded"))
        automatic = html.escape(str(row.get("failure_type") or "Not scored"))
        outcome = html.escape(
            {
                "passed": "No issue detected",
                "failed": "Issue detected",
                "unresolved": "Needs review",
                "execution_error": "No usable answer",
                "cancelled": "Cancelled",
                "skipped": "Skipped",
            }.get(row.get("automatic_outcome") or _automatic_outcome(row), "Not recorded")
        )
        determination = html.escape(
            {"determined": "Check completed", "unable_to_determine": "Could not determine"}.get(
                row.get("determination_state"), "Not recorded"
            )
        )
        findings = html.escape(detail["why_failed"])
        note = html.escape(str(row.get("review_note") or "No source review recorded."))
        reviewer = html.escape(str(row.get("reviewer") or "Not recorded"))
        kind = html.escape(str(row.get("reviewer_kind") or "not_recorded").replace("_", " "))
        evidence = []
        for source in detail["source_passages"]:
            name = html.escape(source["document"])
            location = html.escape(source["location"])
            passage = html.escape(source["passage"])
            evidence.append(f"<li><strong>{name}</strong> · {location}<blockquote>{passage}</blockquote></li>")
        sources = (
            f"<details><summary>Supplied reference evidence ({len(evidence)} passages)</summary>"
            "<p class='small'>Reference passages supplied for review; this is not client retrieval evidence.</p>"
            f"<ul>{''.join(evidence)}</ul></details>"
            if evidence
            else "<p>No reference passages recorded.</p>"
        )
        cases.append(
            f"<article class='case'><h3>{question}</h3>"
            f"<p class='review-state {decision}'>Review decision: {html.escape(label)}</p>"
            f"<p class='small'>Automatic outcome: {outcome}; determination: {determination}.</p>"
            f"<p class='small'>Advisory finding: {automatic}. {findings} Reviewer: {reviewer} ({kind}).</p>"
            f"<p><strong>Actual answer</strong></p><blockquote>{answer}</blockquote>"
            f"<p><strong>Review note:</strong> {note}</p>{sources}</article>"
        )
    return (
        "<section class='review-summary'><h2>Review completion</h2>"
        f"<p class='review-state'>{html.escape(count_text)}</p><p>{html.escape(decisions_text)}</p>"
        f"<p>{html.escape(participation)}</p>"
        "<p>Pending answers have no reviewed decision, even when the automatic assessment passes. "
        "Offline response review provides no launch verdict.</p></section>"
        f"<h2>Case findings</h2>{''.join(cases)}"
    )


def _run_manifests(df: pd.DataFrame, redact_personal_data: bool) -> list[dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for record in df.to_dict(orient="records"):
        manifest = _parse_manifest(record.get("manifest"))
        if not manifest:
            continue
        original_hash = manifest.get("manifest_hash")
        actual_hash = version_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
        exported = _safe_export(manifest, redact_personal_data)
        key = version_hash(exported)
        if key not in snapshots:
            snapshots[key] = {
                "run_ids": [],
                "original_manifest_hash": original_hash,
                "original_hash_status": "verified"
                if original_hash == actual_hash
                else "mismatch"
                if original_hash
                else "not_recorded",
                "exported_manifest_hash": key,
                "redacted": version_hash(manifest) != key,
                "manifest": exported,
            }
        run_id = record.get("run_id")
        if run_id is not None and not pd.isna(run_id) and str(run_id) not in snapshots[key]["run_ids"]:
            snapshots[key]["run_ids"].append(str(run_id))
    return list(snapshots.values())


def _manifest_values(df: pd.DataFrame) -> list[dict[str, Any]]:
    if "manifest" not in df:
        return []
    values = [_parse_manifest(value) for value in df["manifest"]]
    unique = {version_hash(value): value for value in values if value}
    return list(unique.values())


def _parse_manifest(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass
    return {}


def _manifest_nested_values(manifests: list[dict[str, Any]], parent: str, field: str) -> list[str]:
    return sorted(
        {
            str(value[parent][field])
            for value in manifests
            if isinstance(value.get(parent), dict) and value[parent].get(field)
        }
    )


def _safe_export(value: Any, redact_personal_data: bool) -> Any:
    safe = redact_secrets(_safe_mapping_keys(_finite_json_values(value)), preserve_references=False)
    return _redact_nested_pii(safe) if redact_personal_data else safe


def _safe_mapping_keys(value: Any) -> Any:
    """Redact dynamic labels before credential-key rules inspect their values."""
    if isinstance(value, dict):
        return {
            str(redact_secrets(str(key), preserve_references=False)): _safe_mapping_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_mapping_keys(item) for item in value]
    return value


def _finite_json_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _finite_json_values(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_finite_json_values(item) for item in value]
    if isinstance(value, Real) and not math.isfinite(value):
        return None
    return value


def _csv_payload(payload: dict[str, Any]) -> str:
    safe = pd.DataFrame(payload["executions"])
    if not safe.empty:
        safe["report_gate_configuration_version"] = payload["gate_configuration_version"]
        safe["report_gate_configuration"] = json.dumps(payload["gate_configuration"], ensure_ascii=False)
        safe["report_candidate_verdicts"] = json.dumps(
            {name: value["verdict"] for name, value in payload["candidates"].items()}, ensure_ascii=False
        )
    for column in safe:
        safe[column] = safe[column].apply(
            lambda value: json.dumps(value, ensure_ascii=False, default=str)
            if isinstance(value, dict | list | tuple)
            else _csv_safe(value)
        )
    return safe.to_csv(index=False)


def _redact_nested_pii(value: Any) -> Any:
    if isinstance(value, dict):
        return {redact_pii(str(key)): _redact_nested_pii(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_nested_pii(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_nested_pii(item) for item in value)
    return redact_pii(str(value)) if isinstance(value, str) else value


def _unique(df: pd.DataFrame, column: str, *, missing: str | None = None) -> list[str]:
    if df.empty:
        return []
    if column not in df:
        return [missing] if missing is not None else []
    values = {str(value) for value in df[column].dropna() if str(value).strip()}
    if missing is not None and (df[column].isna().any() or df[column].astype(str).str.strip().eq("").any()):
        values.add(missing)
    return sorted(values)


def _flattened_unique(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df:
        return []
    return sorted(
        {str(item) for value in df[column] if isinstance(value, list | tuple) for item in value if str(item).strip()}
    )


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


def _html_payload(payload: dict[str, Any]) -> str:
    candidates = payload["candidates"]
    metadata = payload["metadata"]
    counts = metadata["execution_counts"]
    review_section = _review_html(payload)
    automatic = payload["automatic_outcomes"]
    automatic_summary = (
        f"Automatic assessments: {automatic['passed']} pass labels; "
        f"{automatic['failed']} failure outcomes; {automatic['unresolved']} unresolved assessments; "
        f"{automatic['execution_error']} execution errors; {automatic['cancelled']} cancelled; {automatic['skipped']} skipped. "
        "Unresolved assessments need review and are not counted as demonstrated answer failures. "
        "Automatic labels are separate from source review decisions."
    )

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
    }.get(metadata["evidence_classification"], "Imported answers: no launch verdict")
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
    for number, row in enumerate(payload["executions"], start=1):
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
            payload,
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
{_evidence_banner_html(payload)}
{review_section}
<p>Use this report to decide what to inspect and change next. A human owns the release decision.
Automated scores summarize checks on these cases; they are not a safety certification or a measured chance of correctness.</p>
<h2>What was checked</h2>{table(count_rows)}
<p>{escape(automatic_summary)}</p>
<p>Unusable calls are excluded from answer-quality averages and still count against execution requirements.</p>
<h2>Candidate verdicts</h2>{''.join(candidate_sections) or '<p>No candidate evidence was recorded.</p>'}
<h2>Evidence limits</h2>{list_html(metadata['limitations'])}
<h2>Question-by-question evidence</h2>{"Reviewed case evidence appears above." if review_section else "".join(case_sections) or "<p>No checks were recorded.</p>"}
<footer><p>Detected personal data and secrets are redacted. Review this report before sharing: automated redaction cannot identify every confidential detail.
Use the technical JSON or CSV export when an engineer needs the complete evidence record and exact version identifiers.</p></footer>
<details><summary>Technical evidence and provenance</summary><p>Exact settings, version identifiers, and complete records are preserved in the downloadable JSON or CSV report. They do not independently prove source authenticity or human participation.</p></details>
<script type="application/json" id="report-evidence">{evidence_json}</script>
</main></body></html>"""


def _gate_manifest(gates: LaunchGateConfig | None) -> dict[str, Any]:
    configuration = asdict(gates or LaunchGateConfig())
    return {
        "configuration": configuration,
        "version": version_hash(configuration),
        "scope": "Report-time launch assessment; original run and scoring provenance are preserved.",
    }
