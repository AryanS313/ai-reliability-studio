"""Report plumbing regression fixtures; the fabricated scores are not quality evidence."""

from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src import cli
from src.aggregation import LaunchGateConfig, evaluate_candidates
from src.reporting import (
    LOCAL_RETRIEVAL_SCOPE,
    build_report_payload,
    csv_report,
    html_report,
    json_report,
    render_report_payload,
    validate_launch_gates,
)
from src.versioning import version_hash


def _rows() -> pd.DataFrame:
    manifest = {
        "dataset": {"content_hash": "dataset-fixture"},
        "documents": [{"version": "source-fixture"}],
        "model": {"provider": "fixture-provider"},
        "environment": "test",
        "created_at": "2026-09-07T00:00:00+00:00",
        "evaluators": [{"version": "evaluator-fixture", "threshold_version": "threshold-fixture"}],
        "notes": "Contact person@example.com; sk-secret-value-123456",
    }
    manifest["manifest_hash"] = version_hash(manifest)
    return pd.DataFrame(
        [
            {
                "case_id": f"case-{index}",
                "question": "Fictional fixture question",
                "execution_status": "passed",
                "failure_type": "Passed",
                "failure_labels": [],
                "category": "Policy",
                "overall_score": 0.95,
                "groundedness_score": 0.95,
                "citation_correctness_score": 0.95,
                "escalation_correctness_score": 1.0,
                "latency_ms": 10,
                "estimated_cost": 0.0,
                "calibration_status": "calibrated",
                "dataset_launch_eligible": True,
                "target_type": "external_api",
                "run_id": 17,
                "manifest": manifest,
                "human_review_status": "not_reviewed",
                "evaluator_version": "evaluator-fixture",
                "threshold_version": "threshold-fixture",
            }
            for index in range(30)
        ]
    )


@pytest.mark.parametrize("format", ["json", "html", "csv"])
@pytest.mark.parametrize(
    ("gate_values", "calibration_status", "expected_exit", "expected_verdict"),
    [
        ({"minimum_overall_quality": 0.99}, "calibrated", 2, "Needs Improvement"),
        ({"require_calibration": False}, "insufficiently_calibrated", 0, "Ready for Controlled Beta"),
    ],
)
def test_cli_and_report_use_identical_configured_verdict(
    tmp_path, monkeypatch, format, gate_values, calibration_status, expected_exit, expected_verdict
):
    rows = _rows().assign(calibration_status=calibration_status)
    repository = MagicMock()
    monkeypatch.setattr(cli, "SQLiteRepository", lambda _: repository)
    monkeypatch.setattr(cli.database, "set_repository", lambda _: None)
    monkeypatch.setattr(cli, "load_documents", lambda _: [])
    monkeypatch.setattr(cli, "chunk_documents", lambda _: [])
    monkeypatch.setattr(cli, "read_eval_dataset", lambda *_: pd.DataFrame())
    monkeypatch.setattr(cli, "run_evaluation", lambda *_, **__: rows)
    fixture = tmp_path / "fixture.txt"
    fixture.write_text("Fictional data")
    gate_file = tmp_path / "gates.json"
    gate_file.write_text(json.dumps(gate_values))
    output = tmp_path / f"report.{format}"
    exit_code = cli.main(
        [
            "run",
            "--dataset",
            str(fixture),
            "--prompt",
            str(fixture),
            "--document",
            str(fixture),
            "--gate-config",
            str(gate_file),
            "--output",
            str(output),
            "--format",
            format,
        ]
    )
    assert exit_code == expected_exit
    assert expected_verdict in output.read_text()
    gates = validate_launch_gates(LaunchGateConfig(**gate_values))
    if format == "json":
        report = json.loads(output.read_text())
        assert report["candidates"] == json.loads(json.dumps(evaluate_candidates(rows, gates)))
        assert report["gate_configuration"] == json.loads(json.dumps(asdict(gates)))
        assert report["gate_configuration_version"] == version_hash(asdict(gates))
        assert report["metadata"]["gate_configuration_versions"] == [version_hash(asdict(gates))]
        assert report["metadata"]["calibration_status"] == [calibration_status]


@pytest.mark.parametrize(
    "gate_values",
    [
        {"minimum_overall_quality": -1},
        {"minimum_groundedness": float("nan")},
        {"minimum_citation_support": "0.5"},
        {"minimum_sample_size": 0},
        {"maximum_severe_safety_failures": True},
        {"maximum_cost_usd": float("inf")},
        {"maximum_latency_p95_ms": -1},
        {"required_categories": "Policy"},
        {"critical_labels": [""]},
        {"require_calibration": "false"},
        {"unknown_setting": True},
        [],
    ],
)
def test_invalid_cli_gates_fail_before_running_or_creating_database(tmp_path, monkeypatch, gate_values):
    repository = MagicMock()
    monkeypatch.setattr(cli, "SQLiteRepository", repository)
    gate_file = tmp_path / "gates.json"
    gate_file.write_text(json.dumps(gate_values))
    exit_code = cli.main(
        [
            "run",
            "--dataset",
            "missing",
            "--document",
            "missing",
            "--prompt",
            "missing",
            "--gate-config",
            str(gate_file),
        ]
    )
    assert exit_code == cli.EXIT_CONFIGURATION_ERROR
    repository.assert_not_called()


def test_gate_validation_detaches_mutable_configuration_arrays():
    categories = ["Policy"]
    gates = validate_launch_gates(LaunchGateConfig(required_categories=categories))
    categories.append("Billing")
    assert gates.required_categories == ("Policy",)


def test_report_carries_manifest_input_provenance_integrity_and_review_state_without_mutating_input():
    rows = _rows()
    original_manifest = json.loads(json.dumps(rows.iloc[0]["manifest"]))
    report = json.loads(json_report(rows))
    metadata = report["metadata"]
    assert metadata["run_ids"] == ["17"]
    assert metadata["dataset_versions"] == ["dataset-fixture"]
    assert metadata["document_versions"] == ["source-fixture"]
    assert metadata["providers"] == ["fixture-provider"]
    assert metadata["timestamps"] == ["2026-09-07T00:00:00+00:00"]
    assert metadata["environments"] == ["test"]
    assert metadata["evaluator_versions"] == ["evaluator-fixture"]
    assert metadata["threshold_versions"] == ["threshold-fixture"]
    assert metadata["human_review_status"] == ["not_reviewed"]
    assert len(report["run_manifests"]) == 1
    snapshot = report["run_manifests"][0]
    assert snapshot["original_manifest_hash"] == original_manifest["manifest_hash"]
    assert snapshot["original_hash_status"] == "verified"
    assert snapshot["exported_manifest_hash"] == version_hash(snapshot["manifest"])
    assert snapshot["redacted"] is True
    assert snapshot["run_ids"] == ["17"]
    assert "person@example.com" not in json.dumps(report)
    assert "sk-secret-value-123456" not in json.dumps(report)
    assert rows.iloc[0]["manifest"] == original_manifest
    assert report.pop("report_hash") == version_hash(report)


def test_invalid_or_missing_manifest_is_not_claimed_verified_and_rendering_does_not_recompute():
    rows = _rows()
    rows.iloc[0]["manifest"]["dataset"]["content_hash"] = "tampered-fixture"
    payload = build_report_payload(rows)
    assert payload["run_manifests"][0]["original_hash_status"] == "mismatch"
    rows["overall_score"] = 0
    rendered = json.loads(render_report_payload(payload))
    assert next(iter(rendered["candidates"].values()))["verdict"] == "Ready for Controlled Beta"
    without_manifest = build_report_payload(rows.drop(columns=["manifest"]))
    assert without_manifest["run_manifests"] == []
    assert any("No immutable run manifest" in text for text in without_manifest["metadata"]["limitations"])


def test_reports_distinguish_local_retrieval_from_unmeasured_client_metrics_and_preserve_nulls():
    rows = _rows().assign(retrieval_metrics=[{"recall_at_k": 1.0}] * 30, source_retrieval_score=1.0)
    rows["client_latency_ms"] = float("nan")
    for rendered in [json_report(rows), html_report(rows), csv_report(rows)]:
        assert LOCAL_RETRIEVAL_SCOPE in rendered
        assert "not_measured" in rendered
    payload = json.loads(json_report(rows))
    assert payload["metadata"]["retrieval_metrics_scope"] == [LOCAL_RETRIEVAL_SCOPE]
    assert payload["executions"][0]["client_latency_ms"] is None
    assert payload["executions"][0]["retrieval_metrics"]["recall_at_k"] == 1.0
    assert any("local reference retrieval" in text for text in payload["metadata"]["limitations"])


def test_missing_partial_review_or_calibration_is_explicit_and_default_guards_remain():
    rows = _rows()
    rows.at[0, "human_review_status"] = None
    rows.at[0, "calibration_status"] = None
    payload = build_report_payload(rows)
    assert payload["metadata"]["human_review_status"] == ["not_recorded", "not_reviewed"]
    assert payload["metadata"]["calibration_status"] == ["calibrated", "not_recorded"]
    uncalibrated = _rows().assign(calibration_status="insufficiently_calibrated")
    assert next(iter(build_report_payload(uncalibrated)["candidates"].values()))["verdict"] == "Insufficient Evidence"
    synthetic = _rows().assign(target_type="synthetic_mock")
    assert next(iter(build_report_payload(synthetic)["candidates"].values()))["launch_blocked"] is True


def test_explicit_pii_export_setting_does_not_disable_secret_redaction():
    rows = _rows().assign(actual_answer="person@example.com sk-secret-value-123456")
    payload = json.loads(json_report(rows, redact_personal_data=False))
    assert payload["executions"][0]["actual_answer"].startswith("person@example.com")
    assert "sk-secret-value-123456" not in json.dumps(payload)


@pytest.mark.parametrize("format", ["json", "html", "csv"])
def test_replay_cli_exports_supplied_responses_with_no_launch_verdict(tmp_path, monkeypatch, format):
    # Real offline ingestion/scoring/report integration. One fictional answer only.
    monkeypatch.setattr(cli, "SQLiteRepository", MagicMock(side_effect=AssertionError("Replay must not create a DB")))
    dataset = tmp_path / "cases.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "case_id": "offline-fixture",
                    "question": "When can a refund be requested?",
                    "category": "Policy",
                    "expected_behavior": "Answer from policy.",
                    "severity": "low",
                    "tags": ["fixture"],
                    "expected_answer": "Refunds can be requested within 14 days.",
                    "expected_source": "Policy",
                    "should_escalate": False,
                }
            ]
        )
    )
    response = {"case_id": "offline-fixture", "actual_answer": "Refunds can be requested within 14 days."}
    responses = tmp_path / "responses.json"
    responses.write_text(json.dumps([response]))
    document = tmp_path / "policy.md"
    document.write_text("Refunds can be requested within 14 days.")
    pending_output = tmp_path / "pending-review.json"
    pending_code = cli.main(
        [
            "replay",
            "--dataset",
            str(dataset),
            "--responses",
            str(responses),
            "--document",
            str(document),
            "--target-name",
            "Fictional offline assistant",
            "--target-version",
            "fixture-v1",
            "--captured-at",
            "2026-09-07T00:00:00Z",
            "--evidence-kind",
            "fixture",
            "--output",
            str(pending_output),
        ]
    )
    assert pending_code == cli.EXIT_GATE_FAILURE
    pending_row = json.loads(pending_output.read_text())["executions"][0]
    assert pending_row["review_status"] == "pending"
    assert pending_row["human_review_status"] == "not_reviewed"
    reviews = tmp_path / "reviews.json"
    reviews.write_text(
        json.dumps(
            [
                {
                    "case_id": "offline-fixture",
                    "response_hash": version_hash(response),
                    "case_version": pending_row["case_version"],
                    "knowledge_base_version": pending_row["knowledge_base_version"],
                    "decision": "supported",
                    "reviewer": "Fixture reviewer",
                    "reviewer_kind": "ai_assisted",
                    "reviewed_at": "2026-09-07T00:00:00Z",
                    "note": "The answer repeats the fictional supplied policy.",
                }
            ]
        )
    )
    output = tmp_path / f"review.{format}"
    code = cli.main(
        [
            "replay",
            "--dataset",
            str(dataset),
            "--responses",
            str(responses),
            "--document",
            str(document),
            "--target-name",
            "Fictional offline assistant",
            "--target-version",
            "fixture-v1",
            "--captured-at",
            "2026-09-07T00:00:00Z",
            "--evidence-kind",
            "fixture",
            "--reviews",
            str(reviews),
            "--format",
            format,
            "--output",
            str(output),
        ]
    )
    assert code == cli.EXIT_GATE_FAILURE
    rendered = output.read_text()
    assert "Offline response review — no launch verdict" in rendered
    assert "ai_assisted_review_only" in rendered
    if format == "json":
        payload = json.loads(rendered)
        assert payload["metadata"]["evidence_classification"] == "synthetic_fixture"
        assert payload["metadata"]["client_retrieval_status"] == ["not_measured"]
        assert payload["executions"][0]["latency_ms"] is None
        assert payload["executions"][0]["estimated_cost"] is None
        assert payload["executions"][0]["source_retrieval_score"] is None
        assert payload["run_manifests"][0]["original_hash_status"] == "verified"
        assert payload["executions"][0]["review_decision"] == "supported"


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        (["client_supplied"] * 30, "client_supplied_responses"),
        (["fixture"] * 30, "synthetic_fixture"),
        (["fixture", "client_supplied"] * 15, "mixed_or_unknown_imported_responses"),
    ],
)
def test_saved_response_origin_is_classified_without_attesting_authenticity(kinds, expected):
    payload = build_report_payload(_rows().assign(target_type="saved_responses", evidence_kind=kinds))
    assert payload["metadata"]["evidence_classification"] == expected
    assert any("origin is not independently verified" in item for item in payload["metadata"]["limitations"])
    assert all(item["launch_blocked"] for item in payload["candidates"].values())


def test_reviewed_failure_and_pending_answer_are_prominent_despite_automatic_passes():
    rows = (
        _rows()
        .iloc[:3]
        .assign(
            target_type="saved_responses",
            evidence_kind="fixture",
            review_status=["reviewed", "pending", "reviewed"],
            review_decision=["failed", None, "supported"],
            reviewer_kind=["ai_assisted", None, "human"],
            reviewer=["AI reviewer", None, "Declared reviewer"],
            review_note=["Policy limit differs from the answer.", None, "Policy supports this response."],
            actual_answer="The fictional response is shown in full.",
            reference_chunks=[
                [
                    {
                        "source_name": "Policy",
                        "chunk_id": "policy-1",
                        "chunk_text": "The fictional policy permits 14 days.",
                    }
                ]
            ]
            * 3,
        )
    )
    payload = build_report_payload(rows)
    assert payload["review_summary"]["reviewed_responses"] == 2
    assert payload["review_summary"]["pending_responses"] == 1
    assert payload["review_summary"]["decisions"] == {
        "supported": 1,
        "failed": 1,
        "inconclusive": 0,
        "execution_error": 0,
    }
    assert payload["review_summary"]["reviewer_kinds"] == {"ai_assisted": 1, "human": 1}
    assert payload["metadata"]["execution_counts"]["quality_passes"] == 3
    assert "Automatic assessment" in payload["metadata"]["execution_count_scope"]
    rendered = render_report_payload(payload, format="html")
    assert "2 of 3 responses reviewed; 1 pending review." in rendered
    assert "Reviewed decisions: 1 supported; 1 failed; 0 inconclusive; 0 execution errors." in rendered
    assert "Review decision: Pending review" in rendered
    assert "Review decision: Failed" in rendered
    assert "Automatic assessments: 3 pass labels; 0 failure outcomes" in rendered
    assert rendered.index("Review completion") < rendered.index("Case findings") < rendered.index("Candidate verdicts")
    assert "<details><summary>Technical evidence and provenance</summary>" in rendered
    assert "Supplied reference evidence (1 passages)" in rendered
    assert "this is not client retrieval evidence" in rendered
    assert "Policy limit differs from the answer." in rendered
    assert "The fictional policy permits 14 days." in rendered


def test_compact_findings_escape_source_response_and_review_markup():
    rows = (
        _rows()
        .iloc[:1]
        .assign(
            target_type="saved_responses",
            review_status="reviewed",
            review_decision="failed",
            reviewer_kind="ai_assisted",
            actual_answer="<script>alert('answer')</script>",
            reviewer="<img src=x>",
            review_note="<script>alert('review')</script>",
            reference_chunks=[
                [{"source_name": "<b>Policy</b>", "chunk_id": "source-1", "chunk_text": "<script>source</script>"}]
            ],
        )
    )
    rendered = html_report(rows)
    assert "<script>" not in rendered
    assert "<img src=x>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;b&gt;Policy&lt;/b&gt;" in rendered


def test_automatic_uncertainty_is_separate_from_failure_and_review_completion():
    rows = (
        _rows()
        .iloc[:7]
        .assign(
            target_type="saved_responses",
            review_status="pending",
            failure_type=[
                "Passed",
                "Needs Review",
                "Reference Evidence Missing",
                "Policy Contradiction",
                "Execution Error",
                "Passed",
                "Policy Contradiction",
            ],
            determination_state=[
                "determined",
                "unable_to_determine",
                "unable_to_determine",
                "determined",
                "unable_to_determine",
                "unable_to_determine",
                "unable_to_determine",
            ],
            execution_status=["passed", "passed", "passed", "passed", "timed_out", "passed", "passed"],
            failure_labels=[
                [],
                ["evaluator_uncertain"],
                ["reference_evidence_missing"],
                ["policy_contradiction"],
                ["infrastructure_failure"],
                [],
                ["policy_contradiction"],
            ],
        )
    )
    payload = build_report_payload(rows)
    counts = payload["automatic_outcomes"]
    assert {key: counts[key] for key in ("passed", "failed", "unresolved", "execution_error")} == {
        "passed": 1,
        "failed": 1,
        "unresolved": 4,
        "execution_error": 1,
    }
    assert [row["automatic_outcome"] for row in payload["executions"]] == [
        "passed",
        "unresolved",
        "unresolved",
        "failed",
        "execution_error",
        "unresolved",
        "unresolved",
    ]
    assert payload["executions"][-1]["failure_labels"] == ["policy_contradiction"]
    assert payload["review_summary"]["pending_responses"] == 7
    rendered = render_report_payload(payload, format="html")
    assert "1 failure outcomes; 4 unresolved assessments; 1 execution errors" in rendered
    assert "not counted as demonstrated answer failures" in rendered
    assert "Automatic outcome: unresolved; determination: unable_to_determine" in rendered
    assert "Advisory classifier label: Policy Contradiction" in rendered
    assert "policy_contradiction" in rendered


@pytest.mark.parametrize(
    ("kind", "banner"),
    [
        ("fixture", "Fictional workflow rehearsal — no real assistant or customer evidence."),
        ("client_supplied", "Client-supplied responses — origin and live execution are not independently verified."),
    ],
)
def test_evidence_origin_is_prominent_before_review_and_findings(kind, banner):
    rows = _rows().iloc[:2].assign(target_type="saved_responses", evidence_kind=kind, review_status="pending")
    rendered = html_report(rows)
    assert rendered.index(banner) < rendered.index("Review completion") < rendered.index("Case findings")
    assert "aria-label='Evidence classification'" in rendered


@pytest.mark.parametrize(("provider", "model"), [("fixture-provider", "fixture-model"), (None, None)])
def test_persisted_observed_identity_roundtrip_never_uses_configured_runner_defaults(tmp_path, provider, model):
    from src.storage import SQLiteRepository

    repository = SQLiteRepository(tmp_path / "identity.sqlite3")
    context = repository.local_context()
    run_id = repository.create_run(
        context,
        run_name="Identity fixture",
        model_name="mock-model",
        mode="test",
        unique_case_count=1,
        total_executions=1,
        target_type="external_api",
    )
    identity = {
        "provenance": "target_response" if provider or model else "not_reported",
        "reported_provider": provider,
        "reported_model": model,
        "configured_runner_provider": None,
        "configured_runner_model": "mock-model",
        "target_type": "external_api",
    }
    row = _rows().iloc[0].to_dict()
    row.update({"model_name": "mock-model", "provider": "external_api", "metadata": {"model_identity": identity}})
    repository.save_result(context, run_id, row)
    persisted = pd.DataFrame(repository.list_results(context, run_id))
    payload = build_report_payload(persisted)
    assert payload["metadata"]["providers"] == ([provider] if provider else [])
    assert payload["metadata"]["models"] == ([model] if model else [])
    assert payload["metadata"]["model_identity_provenance"] == [identity["provenance"]]
    assert payload["executions"][0]["provider"] == provider
    assert payload["executions"][0]["model_name"] == model
    assert payload["executions"][0]["configured_runner_model"] == "mock-model"
    assert persisted.iloc[0]["model_name"] == "mock-model"
