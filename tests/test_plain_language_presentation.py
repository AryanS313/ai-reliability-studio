from __future__ import annotations

import json

import pandas as pd
import pytest

from src.aggregation import LaunchGateConfig, evaluate_candidate
from src.presentation import (
    candidate_title,
    failure_presentation,
    metric_display,
    metric_label,
    readiness_check_rows,
    version_difference_rows,
)


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("overall_score", 0.8, "80%"),
        ("minimum_groundedness", 0.755, "75.5%"),
        ("maximum_execution_error_rate", 0, "0%"),
        ("maximum_unsupported_claim_rate", 0.125, "12.5%"),
        ("maximum_latency_p95_ms", 1234.5, "1,234.5 ms"),
        ("maximum_cost_usd", 0, "$0.00"),
        ("estimated_cost", 0.000123, "$0.000123"),
        ("minimum_sample_size", 30, "30"),
        ("maximum_severe_safety_failures", 1, "1"),
    ],
)
def test_metrics_display_backend_units_without_changing_scale(name, value, expected):
    assert metric_display(name, value) == expected
    assert "_" not in metric_label(name)


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf"), True, {}, [], "unknown"])
def test_missing_or_invalid_measurements_never_become_zero(value):
    assert metric_display("total_cost_usd", value) == "Not measured"


def test_metric_deltas_show_percentage_points_and_preserve_small_costs():
    assert metric_display("overall_score", 0.025, delta=True) == "+2.5 percentage points"
    assert metric_display("groundedness_score", -0.03, delta=True) == "-3 percentage points"
    assert metric_display("total_cost_usd", -0.001, delta=True) == "−$0.001"
    assert metric_display("latency_ms", 200, delta=True) == "+200 ms"
    assert metric_display("total_cost_usd", 1e-14) != "$0.00"
    assert metric_label("opaque_metric_deadbeef") == "Additional measurement"


def test_readiness_rows_preserve_recorded_results_and_unknown_measurements():
    rows = readiness_check_rows(
        {
            "gate_results": [
                {"name": "minimum_overall_quality", "actual": 0.8, "threshold": 0.75, "passed": True},
                {"name": "maximum_latency_p95_ms", "actual": 1250, "threshold": 1000, "passed": False},
                {"name": "maximum_cost_usd", "actual": None, "threshold": 1.25, "passed": False},
                {"name": "minimum_sample_size", "actual": 3, "passed": True},
                {"name": "minimum_groundedness", "actual": 0.8, "threshold": 0.8, "passed": False},
            ]
        }
    )
    assert rows[0] == {
        "Check": "Overall answer quality",
        "Result": "Met",
        "What it means": "Measured 80%; requires at least 75%.",
    }
    assert rows[1]["Result"] == "Not met"
    assert "1,250 ms" in rows[1]["What it means"]
    assert rows[2]["Result"] == "Unknown"
    assert "Not measured" in rows[2]["What it means"]
    assert "$1.25" in rows[2]["What it means"]
    assert "$0.00" not in rows[2]["What it means"]
    assert rows[3]["Result"] == "Unknown"
    assert "limit was not recorded" in rows[3]["What it means"]
    assert rows[4]["Result"] == "Not met"
    assert "rounded" in rows[4]["What it means"]


def test_readiness_rows_handle_missing_unknown_and_malformed_checks_without_false_pass():
    assert readiness_check_rows({})[0]["Result"] == "Not available"
    rows = readiness_check_rows(
        {
            "gate_results": [
                {"name": "opaque_gate_id_abc123", "passed": "true", "explanation": "{'private': 'person@example.com'}"},
                "unusable",
            ]
        }
    )
    assert all(row["Result"] == "Unknown" for row in rows)
    visible = json.dumps(rows)
    assert "opaque_gate" not in visible
    assert "person@example.com" not in visible
    assert "{'" not in visible
    missing = readiness_check_rows({"gate_results": [{"name": "minimum_overall_quality", "passed": True}]})
    assert missing[0]["Result"] == "Unknown"
    assert "measurement and required limit were not recorded" in missing[0]["What it means"]


def test_category_coverage_formats_missing_topics_without_python_list_or_personal_data():
    rows = readiness_check_rows(
        {
            "gate_results": [
                {
                    "name": "required_category_coverage",
                    "passed": False,
                    "explanation": "Missing categories: ['Refunds', 'Support person@example.com']",
                }
            ]
        }
    )
    assert rows[0]["Result"] == "Not met"
    assert "Add cases for: Refunds, Support" in rows[0]["What it means"]
    assert "['" not in rows[0]["What it means"]
    assert "person@example.com" not in rows[0]["What it means"]


def test_actual_aggregation_checks_all_have_readable_names_and_descriptions():
    frame = pd.DataFrame(
        [
            {
                "case_id": "opaque-case-1",
                "target_type": "external_api",
                "execution_status": "passed",
                "failure_type": "Needs Review",
                "failure_labels": ["evaluator_uncertain"],
                "determination_state": "unable_to_determine",
                "overall_score": 0.7,
                "groundedness_score": 0.7,
                "citation_correctness_score": 0.7,
                "escalation_correctness_score": 0.7,
                "latency_ms": 500,
                "estimated_cost": 0.001,
                "category": "Refunds",
            }
        ]
    )
    evaluation = evaluate_candidate(
        frame,
        LaunchGateConfig(maximum_cost_usd=1, maximum_latency_p95_ms=1000, required_categories=("Refunds", "Safety")),
    )
    rows = readiness_check_rows(evaluation)
    assert len(rows) == len(evaluation["gate_results"])
    assert all(row["Check"] != "Additional release check" for row in rows)
    for gate, row in zip(evaluation["gate_results"], rows, strict=True):
        assert gate["name"] not in row["Check"]
        assert gate["name"] not in row["What it means"]
        if gate["passed"] is False:
            assert row["Result"] != "Met"
    assert "['" not in json.dumps(rows)


def test_actual_synthetic_and_failed_execution_checks_cannot_appear_ready():
    sample = evaluate_candidate(
        pd.DataFrame([{"target_type": "synthetic_mock", "case_id": "sample", "failure_type": "Passed"}])
    )
    rows = readiness_check_rows(sample)
    assert rows[0]["Check"] == "Evidence from a real assistant"
    assert rows[0]["Result"] == "Not met"
    assert "cannot establish" in rows[0]["What it means"]
    failed = evaluate_candidate(
        pd.DataFrame(
            [
                {
                    "target_type": "external_api",
                    "case_id": "failed",
                    "execution_status": "failed",
                    "failure_type": "Execution Error",
                }
            ]
        )
    )
    rows = readiness_check_rows(failed)
    assert rows[0]["Check"] == "Answers available to evaluate"
    assert rows[0]["Result"] == "Not met"
    assert "do not receive quality scores" in rows[0]["What it means"]


def test_candidate_titles_use_human_names_and_never_generated_identity():
    candidate = {
        "target_type": "foundation_model",
        "target_name": "Foundation Model",
        "prompt_name": "Refund instructions",
        "model_name": "Example model",
        "candidate_id": "deadbeef" * 8,
        "display_name": "Raw · vdeadbeef",
        "short_version": "deadbeef",
    }
    assert candidate_title(candidate) == "Example model · Refund instructions"
    assert candidate_title({"candidate": candidate}) == candidate_title(candidate)
    assert (
        candidate_title({**candidate, "target_type": "synthetic_mock", "model_name": "mock-provider"})
        == "Sample assistant · Refund instructions"
    )
    assert (
        candidate_title(
            {
                "target_type": "external_api",
                "target_name": "Customer support",
                "prompt_name": "Updated refund guidance · vdeadbeef",
            }
        )
        == "Customer support · Updated refund guidance"
    )
    assert (
        candidate_title(
            {"target_type": "foundation_model", "model_name": "Unknown model", "prompt_name": "deadbeef" * 8}
        )
        == "Connected assistant"
    )
    assert candidate_title(None) == "Assistant evaluation"


@pytest.mark.parametrize("stored_name", ["Improved Prompt", "Candidate Prompt"])
def test_candidate_instruction_names_do_not_claim_unproven_improvement(stored_name):
    assert (
        candidate_title({"target_type": "synthetic_mock", "prompt_name": stored_name})
        == "Sample assistant · Candidate instructions"
    )
    assert (
        candidate_title({"target_type": "synthetic_mock", "prompt_name": "Current Prompt"})
        == "Sample assistant · Current instructions"
    )


def test_version_comparison_reports_missing_mixed_and_changed_without_ids():
    rows = version_difference_rows(
        {
            "versions": {
                "baseline": {
                    "dataset_version": ["abc123"],
                    "prompt_version": ["old-id"],
                    "evaluator_version": ["v1", "v2"],
                    "calibration_version": [],
                },
                "candidate": {
                    "dataset_version": ["abc123"],
                    "prompt_version": ["new-id"],
                    "evaluator_version": ["v2"],
                    "calibration_version": ["private-id"],
                },
            }
        }
    )
    by_setting = {row["Setting"]: row for row in rows}
    assert by_setting["Evaluation cases"]["Comparison"] == "Unchanged"
    assert by_setting["Assistant instructions"]["Comparison"] == "Changed"
    assert by_setting["Evaluation method"]["Baseline"] == "2 different versions"
    assert by_setting["Evaluation method"]["Comparison"] == "Not enough information"
    assert by_setting["Human review calibration"]["Baseline"] == "Not recorded"
    visible = json.dumps(rows)
    assert all(value not in visible for value in ("abc123", "old-id", "new-id", "private-id"))
    assert version_difference_rows({}) == []


def test_failure_evidence_hides_identifiers_but_keeps_technical_records():
    detail = failure_presentation(
        {
            "case_id": "case-private-abc123",
            "candidate_id": "candidate-private-def456",
            "failure_type": "Privacy Violation",
            "failure_labels": ["privacy_violation"],
            "failure_reason_codes": ["runtime_credential_disclosure", "unrecognized_backend_check_id"],
            "expected_behavior": "refuse_and_escalate",
            "actual_answer": "Contact person@example.com.",
            "failure_evidence": {"runtime_credential_disclosure": [{"reason_code": "runtime_credential_disclosure"}]},
            "retrieved_chunks": [
                {"document_id": "document-internal-id", "chunk_id": "chunk-internal-id", "text": "Policy evidence."}
            ],
        }
    )
    assert detail["summary"] == "Privacy Violation."
    assert "may disclose private information" in detail["why_failed"]
    assert "disclosure blocks release" in detail["why_failed"]
    assert "additional finding requires review" in detail["why_failed"]
    assert "unrecognized_backend" not in detail["why_failed"]
    assert "runtime_credential_disclosure" not in detail["why_failed"]
    assert detail["expected_behavior"] == "Decline the request and hand off the case to an authorized person."
    assert detail["source_passages"][0]["document"] == "Reference document"
    assert detail["source_passages"][0]["location"] == "Retrieved passage"
    assert "person@example.com" not in detail["actual_behavior"]
    assert detail["technical_metadata"]["case_id"] == "case-private-abc123"
    assert "runtime_credential_disclosure" in detail["raw_evaluator_output"]["failure_evidence"]
    assert failure_presentation({"failure_type": "opaque-code-abc123"})["root_cause"] == "Answer needs review"


def test_failure_source_location_and_nested_relationship_remain_inspectable():
    detail = failure_presentation(
        {
            "failure_type": "Expected Answer Mismatch",
            "expected_answer": "Exact expected behavior.",
            "expected_behavior": "answer",
            "score_explanation": {"correctness": {"relationship": {"classification": "missing_constraint"}}},
            "retrieved_chunks": [
                {"source_name": "Refund policy", "page": 2, "section": "Exceptions", "chunk_id": "do-not-render"},
                {"page": 0, "chunk_id": "another-internal-id"},
            ],
        }
    )
    assert "may omit a required condition" in detail["why_failed"]
    assert detail["expected_behavior"] == "Exact expected behavior."
    assert detail["source_passages"][0]["location"] == "Page 2 · Exceptions"
    assert detail["source_passages"][1]["location"] == "Page 0"
    assert "do-not-render" not in json.dumps(detail["source_passages"])


@pytest.mark.parametrize(
    ("failure_type", "next_step"),
    [("Source Retrieval Failure", "try finding more passages"), ("Privacy Violation", "Remove personal details")],
)
def test_recommended_actions_are_understandable_without_technical_settings(failure_type, next_step):
    action = failure_presentation({"failure_type": failure_type})["recommended_action"]
    assert next_step in action
    assert "top_k" not in action
    assert "PII" not in action
