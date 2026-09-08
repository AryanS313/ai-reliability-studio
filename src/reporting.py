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
from src.presentation import execution_summary, safe_nested
from src.security import redact_pii, redact_secrets
from src.versioning import version_hash

REPORT_SCHEMA_VERSION = "2.0"
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
    df = _hydrate_model_identity(df)
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
    payload = _safe_export(payload, redact_personal_data)
    payload["report_hash"] = version_hash(payload)
    return payload


def render_report_payload(payload: dict[str, Any], *, format: str = "json") -> str:
    """Render an already computed snapshot without re-evaluating its launch gates."""
    if format == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False, default=str, allow_nan=False)
    if format == "csv":
        return _csv_payload(payload)
    if format != "html":
        raise ValueError(f"Unsupported report format: {format}")
    summary_rows = []
    for name, result in payload["candidates"].items():
        summary_rows.append(
            f"<tr><td>{html.escape(name)}</td><td>{html.escape(str(result['verdict']))}</td>"
            f"<td>{html.escape(json.dumps(result.get('metrics', {}), default=str))}</td>"
            f"<td>{html.escape(json.dumps(result.get('gate_results', []), default=str))}</td></tr>"
        )
    execution_table = pd.DataFrame(payload["executions"]).to_html(index=False, escape=True)
    metadata_table = pd.DataFrame(
        [
            {"field": key, "value": json.dumps(value, ensure_ascii=False, default=str)}
            for key, value in payload["metadata"].items()
        ]
    ).to_html(index=False, escape=True)
    gate_text = html.escape(json.dumps(payload["gate_configuration"], indent=2))
    manifest_text = html.escape(json.dumps(payload["run_manifests"], ensure_ascii=False, indent=2, default=str))
    evidence_banner = _evidence_banner_html(payload)
    review_section = _review_html(payload)
    limitations = "".join(f"<li>{html.escape(str(item))}</li>" for item in payload["metadata"]["limitations"])
    counts = payload["automatic_outcomes"]
    automatic_summary = (
        f"Automatic assessments: {counts['passed']} pass labels; "
        f"{counts['failed']} failure outcomes; {counts['unresolved']} unresolved assessments; "
        f"{counts['execution_error']} execution errors; {counts['cancelled']} cancelled; {counts['skipped']} skipped. "
        "Unresolved assessments need review and are not counted as demonstrated answer failures. "
        "Automatic labels are separate from source review decisions."
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>AI Reliability Studio report</title>
<style>body{{font-family:system-ui;margin:2rem auto;padding:0 1rem;max-width:1150px;color:#17202a;line-height:1.5}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #dfe5ee;padding:.45rem;text-align:left;vertical-align:top}}
th{{background:#f5f7fa}}pre,blockquote{{white-space:pre-wrap;overflow-wrap:anywhere}}td{{overflow-wrap:anywhere}}
.case{{border:1px solid #dfe5ee;border-radius:8px;padding:1rem;margin:1rem 0}}.case h3{{margin:.2rem 0}}
.review-summary{{border-left:5px solid #285a83;background:#eef5fb;padding:1rem}}
.review-state{{font-size:1.1rem;font-weight:600}}.pending{{color:#805700}}.failed{{color:#9b2424}}
.small{{font-size:.9rem;color:#485465}}details{{margin:1rem 0}}summary{{cursor:pointer;font-weight:600}}
.technical-table{{overflow-x:auto}}.technical-table table{{font-size:.8rem}}blockquote{{margin:.5rem 0;padding:.5rem 1rem;background:#f7f9fc}}</style></head>
<body><h1>AI Reliability Studio report</h1>
{evidence_banner}
{review_section}
<h2>Candidate verdicts</h2><table><thead><tr><th>Candidate</th><th>Verdict</th><th>Automatic metrics</th><th>Gate checks</th></tr></thead>
<tbody>{''.join(summary_rows)}</tbody></table>
<h2>Automatic assessment summary</h2><p>{html.escape(automatic_summary)}</p>
<p>Automatic metrics exclude infrastructure failures. Synthetic runs cannot establish launch readiness.</p>
<h2>Evidence limits</h2><ul>{limitations}</ul>
<details><summary>Technical evidence and provenance</summary>
<h2>Run metadata (execution counts describe automatic assessments)</h2>{metadata_table}
<h2>Report gate configuration</h2><p>Version: {html.escape(payload['gate_configuration_version'])}</p><pre>{gate_text}</pre>
<h2>Run manifest snapshots</h2><pre>{manifest_text}</pre>
<h2>Raw execution records</h2><div class="technical-table">{execution_table}</div></details>
<p class="small">Report content hash: {html.escape(payload['report_hash'])}</p></body></html>"""


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
    df = _hydrate_model_identity(df)
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
        evidence_classification = "real_target" if target_types else "unknown"
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
        case_id = html.escape(str(row.get("case_id") or "Unidentified case"))
        question = html.escape(str(row.get("question") or "Question not recorded"))
        answer = html.escape(str(row.get("actual_answer") or "No answer recorded"))
        automatic = html.escape(str(row.get("failure_type") or "Not scored"))
        outcome = html.escape(str(row.get("automatic_outcome") or _automatic_outcome(row)))
        determination = html.escape(str(row.get("determination_state") or "not_recorded"))
        flags = html.escape(json.dumps(row.get("failure_labels") or [], ensure_ascii=False, default=str))
        note = html.escape(str(row.get("review_note") or "No source review recorded."))
        reviewer = html.escape(str(row.get("reviewer") or "Not recorded"))
        kind = html.escape(str(row.get("reviewer_kind") or "not_recorded").replace("_", " "))
        chunks = row.get("reference_chunks") or row.get("retrieved_chunks") or []
        evidence = []
        for chunk in chunks if isinstance(chunks, list) else []:
            if not isinstance(chunk, dict):
                continue
            name = html.escape(str(chunk.get("source_name") or "Unnamed source"))
            location = html.escape(str(chunk.get("chunk_id") or chunk.get("section") or "Location not recorded"))
            passage = html.escape(str(chunk.get("chunk_text") or chunk.get("text") or "Passage text not recorded"))
            evidence.append(f"<li><strong>{name}</strong> · {location}<blockquote>{passage}</blockquote></li>")
        sources = (
            f"<details><summary>Supplied reference evidence ({len(evidence)} passages)</summary>"
            "<p class='small'>Reference passages supplied for review; this is not client retrieval evidence.</p>"
            f"<ul>{''.join(evidence)}</ul></details>"
            if evidence
            else "<p>No reference passages recorded.</p>"
        )
        cases.append(
            f"<article class='case'><h3>{case_id} · {question}</h3>"
            f"<p class='review-state {decision}'>Review decision: {html.escape(label)}</p>"
            f"<p class='small'>Automatic outcome: {outcome}; determination: {determination}.</p>"
            f"<p class='small'>Advisory classifier label: {automatic}; flags: {flags}. Reviewer: {reviewer} ({kind}).</p>"
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
    safe = redact_secrets(_finite_json_values(value), preserve_references=False)
    return _redact_nested_pii(safe) if redact_personal_data else safe


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
        return {key: _redact_nested_pii(item) for key, item in value.items()}
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
