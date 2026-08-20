from __future__ import annotations

import pandas as pd
import pytest

from src.aggregation import LaunchGateConfig, evaluate_candidate
from src.calibration import (
    CalibrationRequirements,
    EvaluatorThresholdConfiguration,
    calibrate_evaluators,
    read_calibration_dataset,
    run_calibration_workflow,
    uncalibrated_status,
)
from src.storage import SQLiteRepository


def _calibration_rows(count: int = 40) -> pd.DataFrame:
    records = []
    for index in range(count):
        positive = index < 10
        labels = ["policy_contradiction"] if positive else []
        records.append(
            {
                "case_id": f"heldout-{index}",
                "split": "holdout",
                "human_labels": labels,
                "automatic_labels": labels,
            }
        )
    records.append(
        {
            "case_id": "development-excluded",
            "split": "development",
            "human_labels": ["policy_contradiction"],
            "automatic_labels": [],
        }
    )
    return pd.DataFrame(records)


def test_calibration_reports_confusion_matrix_and_observed_metrics():
    result = calibrate_evaluators(
        _calibration_rows(),
        labels=["policy_contradiction"],
        requirements=CalibrationRequirements(),
    )
    metric = result["evaluators"]["policy_contradiction"]
    assert result["status"] == "calibrated"
    assert result["reviewed_cases"] == 40
    assert result["excluded_non_holdout_cases"] == 1
    assert metric["confusion_matrix"] == {
        "true_positive": 10,
        "false_positive": 0,
        "true_negative": 30,
        "false_negative": 0,
    }
    assert metric["precision"] == metric["recall"] == metric["f1"] == 1
    assert "Descriptive observed metrics only" in result["statistical_claim"]


def test_small_or_one_class_calibration_is_insufficient_without_confidence_claim():
    result = calibrate_evaluators(
        _calibration_rows(6),
        labels=["policy_contradiction"],
        requirements=CalibrationRequirements(minimum_reviewed_cases=30),
    )
    assert result["status"] == "insufficiently_calibrated"
    assert result["limitations"]
    assert result["evaluators"]["policy_contradiction"]["sample_sufficient"] is False


def test_threshold_versions_are_immutable_inputs_to_calibration():
    first = EvaluatorThresholdConfiguration()
    second = EvaluatorThresholdConfiguration(thresholds={**first.thresholds, "claim_support_overlap": 0.5})
    assert first.version != second.version
    result = calibrate_evaluators(
        _calibration_rows(),
        labels=["policy_contradiction"],
        thresholds=second,
    )
    assert result["threshold_version"] == second.version
    assert result["calibration_version"]
    assert uncalibrated_status(first)["status"] == "insufficiently_calibrated"


def test_duplicate_or_non_heldout_calibration_data_is_rejected_or_flagged():
    duplicate = _calibration_rows().iloc[:2].copy()
    duplicate.loc[1, "case_id"] = duplicate.loc[0, "case_id"]
    with pytest.raises(ValueError, match="unique"):
        calibrate_evaluators(duplicate, labels=["policy_contradiction"])
    development = _calibration_rows().assign(split="development")
    with pytest.raises(ValueError, match="holdout"):
        calibrate_evaluators(development, labels=["policy_contradiction"])


def test_calibration_upload_reader_accepts_supported_formats_and_rejects_malformed_data():
    csv_data = b"case_id,split,human_labels,automatic_labels\ncase-1,holdout,[],[]\n"
    assert read_calibration_dataset("reviews.csv", csv_data).iloc[0]["case_id"] == "case-1"
    jsonl_data = b'{"case_id":"case-2","split":"holdout","human_labels":[],"automatic_labels":[]}\n'
    assert read_calibration_dataset("reviews.jsonl", jsonl_data).iloc[0]["case_id"] == "case-2"
    with pytest.raises(ValueError, match="parsed safely"):
        read_calibration_dataset("reviews.json", b"not json")


def test_launch_verdict_is_insufficient_without_qualifying_calibration():
    rows = pd.DataFrame(
        [
            {
                "case_id": f"case-{index}",
                "execution_status": "passed",
                "failure_type": "Passed",
                "failure_labels": [],
                "category": "Policy",
                "overall_score": 0.95,
                "groundedness_score": 0.95,
                "citation_correctness_score": 0.95,
                "escalation_correctness_score": 1.0,
                "latency_ms": 10,
                "estimated_cost": 0,
                "calibration_status": "insufficiently_calibrated",
                "dataset_launch_eligible": True,
            }
            for index in range(30)
        ]
    )
    result = evaluate_candidate(rows, LaunchGateConfig())
    assert result["verdict"] == "Insufficient Evidence"
    gate = next(item for item in result["gate_results"] if item["name"] == "minimum_evaluator_calibration")
    assert gate["passed"] is False


def test_human_reviews_and_calibration_result_are_workspace_scoped_and_persisted(tmp_path):
    repository = SQLiteRepository(tmp_path / "calibration.sqlite3")
    first = repository.create_workspace("first@example.com", "First")
    second = repository.create_workspace("second@example.com", "Second")
    result = run_calibration_workflow(
        repository,
        first,
        _calibration_rows(),
        evaluator_version="deterministic-v3",
        labels=["policy_contradiction"],
    )
    assert result["calibration_id"] > 0
    assert repository.latest_calibration(first)["result"]["status"] == "calibrated"
    assert repository.latest_calibration(second) is None
    with repository.connection() as conn:
        reviews = conn.execute(
            "SELECT COUNT(*) FROM calibration_reviews WHERE workspace_id = ?", (first.workspace_id,)
        ).fetchone()[0]
    assert reviews == len(_calibration_rows())
