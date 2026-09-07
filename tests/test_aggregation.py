from __future__ import annotations

import pandas as pd

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


def test_partial_calibration_does_not_count_as_fully_calibrated():
    rows = _rows()
    rows.loc[0, "calibration_status"] = None
    result = evaluate_candidate(rows)
    gate = next(item for item in result["gate_results"] if item["name"] == "minimum_evaluator_calibration")
    assert gate["passed"] is False
    assert result["verdict"] == "Insufficient Evidence"


def test_missing_or_invalid_measurements_cannot_pass_configured_budget_gates():
    for missing in (None, float("inf"), -1):
        rows = _rows()
        rows["latency_ms"] = rows["latency_ms"].astype(float)
        rows.loc[0, "latency_ms"] = missing
        rows.loc[0, "estimated_cost"] = missing
        result = evaluate_candidate(rows, LaunchGateConfig(maximum_latency_p95_ms=500, maximum_cost_usd=1))
        assert result["metrics"]["latency_p95_ms"] is None
        assert result["metrics"]["total_cost_usd"] is None
        assert result["metrics"]["cost_measurement_count"] == 34
        gates = {gate["name"]: gate for gate in result["gate_results"]}
        assert gates["maximum_latency_p95_ms"]["passed"] is False
        assert gates["maximum_cost_usd"]["passed"] is False
        assert result["launch_blocked"] is True


def test_cost_budget_includes_reported_cost_of_unsuccessful_executions():
    rows = _rows()
    rows.loc[0, "execution_status"] = "timed_out"
    rows.loc[0, "estimated_cost"] = 10
    result = evaluate_candidate(rows, LaunchGateConfig(maximum_cost_usd=1))
    assert result["metrics"]["total_cost_usd"] > 10
    gate = next(item for item in result["gate_results"] if item["name"] == "maximum_cost_usd")
    assert gate["passed"] is False


def test_high_scores_do_not_override_an_unresolved_evaluator_decision():
    rows = _rows().assign(determination_state="determined")
    rows.loc[0, "determination_state"] = "unable_to_determine"
    result = evaluate_candidate(rows)
    gate = next(item for item in result["gate_results"] if item["name"] == "evaluator_determinations_complete")
    assert gate["passed"] is False
    assert result["verdict"] == "Insufficient Evidence"
