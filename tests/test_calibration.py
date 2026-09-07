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
    validate_calibration_for_run,
)
from src.scoring import EVALUATOR_VERSION, LABEL_SEMANTICS_VERSION
from src.storage import SQLiteRepository
from src.versioning import version_hash


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
        evaluator_version=EVALUATOR_VERSION,
        label_semantics_version=LABEL_SEMANTICS_VERSION,
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
        evaluator_version=EVALUATOR_VERSION,
        label_semantics_version=LABEL_SEMANTICS_VERSION,
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


def _qualified_calibration(**kwargs):
    return calibrate_evaluators(
        _calibration_rows(),
        labels=["policy_contradiction"],
        evaluator_version=kwargs.get("evaluator_version", EVALUATOR_VERSION),
        label_semantics_version=kwargs.get("label_semantics_version", LABEL_SEMANTICS_VERSION),
    )


def test_metrics_without_explicit_version_provenance_are_not_qualifying_calibration():
    result = calibrate_evaluators(_calibration_rows(), labels=["policy_contradiction"])
    assert result["evaluators"]["policy_contradiction"]["precision"] == 1
    assert result["status"] == "insufficiently_calibrated"
    assert any("version" in item for item in result["limitations"])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("evaluator_version", "deterministic-v3", "evaluator version"),
        ("evaluator_version", None, "evaluator version"),
        ("label_semantics_version", "outdated-labels", "label-semantics version"),
        ("label_semantics_version", None, "label-semantics version"),
        ("calibration_version", "invented", "content hash"),
        ("calibration_version", None, "content hash"),
        ("reviewed_cases", 999, "content hash"),
    ],
)
def test_qualifying_calibration_is_bound_to_versions_and_untampered_result(field, value, message):
    result = _qualified_calibration()
    result[field] = value
    with pytest.raises(ValueError, match=message):
        validate_calibration_for_run(
            result,
            EvaluatorThresholdConfiguration(),
            evaluator_version=EVALUATOR_VERSION,
            label_semantics_version=LABEL_SEMANTICS_VERSION,
        )


def test_current_calibration_passes_binding_check_with_workflow_storage_id():
    result = _qualified_calibration()
    validate_calibration_for_run(
        {**result, "calibration_id": 42},
        EvaluatorThresholdConfiguration(),
        evaluator_version=EVALUATOR_VERSION,
        label_semantics_version=LABEL_SEMANTICS_VERSION,
    )


def test_calibration_version_changes_when_evaluator_or_evidence_changes():
    current = _qualified_calibration()
    older = _qualified_calibration(evaluator_version="deterministic-v3")
    assert current["calibration_version"] != older["calibration_version"]
    different_reviews = calibrate_evaluators(
        _calibration_rows().assign(case_id=lambda frame: "other-" + frame["case_id"]),
        labels=["policy_contradiction"],
        evaluator_version=EVALUATOR_VERSION,
        label_semantics_version=LABEL_SEMANTICS_VERSION,
    )
    assert current["evaluators"] == different_reviews["evaluators"]
    assert current["reviewed_dataset_hash"] != different_reviews["reviewed_dataset_hash"]
    assert current["calibration_version"] != different_reviews["calibration_version"]


def test_persisted_calibration_payload_and_hash_include_actual_evaluator_version(tmp_path):
    repository = SQLiteRepository(tmp_path / "versioned-calibration.sqlite3")
    context = repository.local_context()
    original = run_calibration_workflow(
        repository,
        context,
        _calibration_rows(),
        evaluator_version="deterministic-v3",
        labels=["policy_contradiction"],
    )
    stored = repository.latest_calibration(context)
    assert stored["evaluator_version"] == stored["result"]["evaluator_version"] == "deterministic-v3"
    payload = stored["result"]
    assert (
        version_hash({key: value for key, value in payload.items() if key != "calibration_version"})
        == original["calibration_version"]
    )
    with pytest.raises(ValueError, match="evaluator version"):
        validate_calibration_for_run(
            payload,
            EvaluatorThresholdConfiguration(),
            evaluator_version=EVALUATOR_VERSION,
            label_semantics_version=LABEL_SEMANTICS_VERSION,
        )
