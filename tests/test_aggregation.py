from __future__ import annotations

import pandas as pd
import pytest

from src.aggregation import LaunchGateConfig, compare_candidates, evaluate_candidate, evaluate_candidates


def _rows(prompt: str = "baseline", target_type: str = "foundation_model") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": f"case-{index}",
                "question": f"Question {index}",
                "prompt_version": prompt,
                "model_name": "model-a",
                "target_version": "target-1",
                "target_type": target_type,
                "execution_status": "passed",
                "failure_type": "Passed",
                "failure_labels": [],
                "category": "Policy",
                "overall_score": 0.9,
                "groundedness_score": 0.9,
                "citation_correctness_score": 0.9,
                "escalation_correctness_score": 0.9,
                "latency_ms": 100,
                "estimated_cost": 0.01,
                "calibration_status": "calibrated",
                "dataset_launch_eligible": True,
            }
            for index in range(35)
        ]
    )


def test_mock_runs_never_receive_launch_verdict():
    result = evaluate_candidate(_rows(target_type="synthetic_mock"))
    assert result["launch_blocked"] is True
    assert result["verdict"] == "Synthetic demonstration — no launch verdict"


def test_critical_failure_blocks_otherwise_high_average():
    rows = _rows()
    rows.at[0, "failure_labels"] = ["policy_contradiction"]
    result = evaluate_candidate(rows)
    assert result["launch_blocked"] is True
    assert result["verdict"] == "Not Ready"


def test_candidates_get_independent_verdicts_and_counts():
    baseline = _rows("baseline")
    candidate = _rows("candidate")
    candidate["overall_score"] = 0.5
    results = evaluate_candidates(pd.concat([baseline, candidate], ignore_index=True))
    assert len(results) == 2
    assert {value["counts"]["unique_test_cases"] for value in results.values()} == {35}
    assert len({value["verdict"] for value in results.values()}) == 2


def test_execution_failures_are_separate_from_quality_and_comparison_detects_regression():
    baseline = _rows()
    candidate = _rows("candidate")
    candidate["overall_score"] = 0.7
    candidate.loc[:4, "execution_status"] = "timed_out"
    result = evaluate_candidate(candidate, LaunchGateConfig(maximum_execution_error_rate=0.05))
    assert result["counts"]["failed_executions"] == 5
    assert result["counts"]["execution_error_count"] == 5
    comparison = compare_candidates(baseline, candidate)
    assert comparison["regressed"] is True
    assert comparison["metric_deltas"]["overall_score"]["delta"] == -0.2
    assert comparison["infrastructure"]["candidate"]["count"] == 5
    assert comparison["same_quality_case_set"] is False
    assert comparison["limitations"]


def test_quality_failures_are_failures_but_not_execution_errors():
    rows = _rows()
    rows.loc[:2, "failure_type"] = "Grounding Failure"
    result = evaluate_candidate(rows)
    assert result["counts"]["passed_executions"] == 32
    assert result["counts"]["failed_executions"] == 3
    assert result["counts"]["execution_error_count"] == 0
    assert result["counts"]["quality_scored_executions"] == 35
    assert result["counts"]["quality_failed_executions"] == 3
    assert result["metrics"]["execution_error_rate"] == 0


def test_comparison_reports_gate_failure_and_version_differences():
    baseline = _rows().assign(dataset_version="dataset-v1", evaluator_version="eval-v1")
    candidate = _rows("candidate").assign(dataset_version="dataset-v2", evaluator_version="eval-v2")
    candidate.at[0, "failure_type"] = "Policy Contradiction"
    candidate.at[0, "failure_labels"] = ["policy_contradiction"]
    candidate.at[0, "severity"] = "critical"
    comparison = compare_candidates(baseline, candidate)
    assert comparison["new_failures"] == [{"case_id": "case-0", "failure": "policy_contradiction"}]
    assert comparison["versions"]["baseline"]["dataset_version"] == ["dataset-v1"]
    assert comparison["versions"]["candidate"]["evaluator_version"] == ["eval-v2"]
    assert any(
        item["severity"] == "critical" and item["delta"] == 1 for item in comparison["failure_count_deltas"]["severity"]
    )


def test_failed_calls_do_not_satisfy_minimum_quality_sample():
    rows = _rows().iloc[:30].copy()
    rows.loc[0, "execution_status"] = "timed_out"
    result = evaluate_candidate(rows)
    gate = next(item for item in result["gate_results"] if item["name"] == "minimum_sample_size")
    assert gate["actual"] == 29
    assert gate["passed"] is False
    assert result["verdict"] == "Insufficient Evidence"


def test_critical_failure_remains_visible_when_evidence_is_incomplete():
    rows = _rows().iloc[:4].copy()
    rows["calibration_status"] = "insufficiently_calibrated"
    rows.at[0, "failure_labels"] = ["policy_contradiction"]
    result = evaluate_candidate(rows)
    assert result["verdict"] == "Not Ready"
    assert result["launch_blocked"] is True
    assert any(not item["passed"] for item in result["gate_results"] if item["name"] == "minimum_sample_size")


@pytest.mark.parametrize("missing", [None, float("nan"), float("inf"), -1])
def test_missing_invalid_cost_and_latency_cannot_pass_budget_gates(missing):
    rows = _rows().astype({"latency_ms": float})
    rows.loc[0, "estimated_cost"] = missing
    rows.loc[0, "latency_ms"] = missing
    result = evaluate_candidate(rows, LaunchGateConfig(maximum_cost_usd=10, maximum_latency_p95_ms=1000))
    assert result["metrics"]["total_cost_usd"] is None
    assert result["metrics"]["latency_p95_ms"] is None
    gates = {item["name"]: item["passed"] for item in result["gate_results"]}
    assert gates["maximum_cost_usd"] is False
    assert gates["maximum_latency_p95_ms"] is False


def test_cost_includes_failed_call_observations_and_missing_calibration_blocks():
    rows = _rows()
    rows.loc[0, "execution_status"] = "failed"
    rows.loc[0, "estimated_cost"] = 2.0
    rows.loc[1, "calibration_status"] = None
    result = evaluate_candidate(rows, LaunchGateConfig(maximum_cost_usd=1))
    assert result["metrics"]["total_cost_usd"] == pytest.approx(2.34)
    assert result["metrics"]["calibration_status"] == "insufficiently_calibrated"


def test_missing_target_and_string_false_dataset_eligibility_block_launch():
    rows = _rows().drop(columns="target_type")
    rows["dataset_launch_eligible"] = "false"
    result = evaluate_candidate(rows)
    assert result["launch_blocked"] is True
    assert result["verdict"] == "Insufficient Evidence"


def _versioned_rows(prompt="baseline"):
    return _rows(prompt).assign(
        dataset_version="d1", evaluator_version="e1", threshold_version="t1", evaluation_configuration_version="c1"
    )


def test_comparison_ranking_requires_matching_versioned_evidence():
    baseline = _versioned_rows()
    candidate = _versioned_rows("candidate")
    comparison = compare_candidates(baseline, candidate)
    assert comparison["ranking_supported"] is True
    assert comparison["comparison_status"] == "no_material_regression_detected"
    candidate["dataset_version"] = "d2"
    comparison = compare_candidates(baseline, candidate)
    assert comparison["ranking_supported"] is False
    assert comparison["comparison_status"] == "inconclusive"
    assert any("Dataset version" in item for item in comparison["limitations"])


def test_synthetic_and_unversioned_comparisons_cannot_claim_a_winner():
    for rows in [_rows(), _versioned_rows().assign(target_type="synthetic_mock")]:
        comparison = compare_candidates(rows, rows)
        assert comparison["ranking_supported"] is False
        assert comparison["comparison_status"] == "inconclusive"


def test_failed_candidate_case_is_not_reported_as_resolved_quality_failure():
    baseline, candidate = _versioned_rows(), _versioned_rows("candidate")
    baseline.at[0, "failure_labels"] = ["unsupported_claim"]
    candidate.at[0, "execution_status"] = "timed_out"
    comparison = compare_candidates(baseline, candidate)
    assert comparison["resolved_failures"] == []
    assert comparison["ranking_supported"] is False


def test_repeated_case_cannot_inflate_confidence_sample():
    rows = _rows().iloc[:5].copy()
    repeated = pd.concat([rows] * 10, ignore_index=True)
    result = evaluate_candidate(repeated)
    assert result["metrics"]["overall_quality_ci95"] == [None, None]


def test_missing_quality_score_does_not_disappear_into_a_high_average():
    rows = _rows()
    rows.loc[0, "groundedness_score"] = None
    result = evaluate_candidate(rows)
    assert result["verdict"] == "Insufficient Evidence"
    assert result["launch_blocked"] is True
    gate = next(item for item in result["gate_results"] if item["name"] == "quality_measurements_complete")
    assert gate["passed"] is False


def test_one_withheld_secret_in_large_run_cannot_hide_below_error_rate_gate():
    rows = _rows()
    rows.loc[0, "execution_status"] = "invalid_response"
    rows.at[0, "failure_labels"] = ["infrastructure_failure", "privacy_violation", "unsafe_response"]
    result = evaluate_candidate(rows)
    assert result["metrics"]["execution_error_rate"] < 0.05
    assert result["metrics"]["critical_failure_count"] == 1
    assert result["verdict"] == "Not Ready"
