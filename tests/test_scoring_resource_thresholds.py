"""An explicit zero resource threshold is a limit, not a missing setting."""

import pytest

from src import config
from src.calibration import EvaluatorThresholdConfiguration, validate_calibration_for_run
from src.scoring import EVALUATOR_VERSION, LABEL_SEMANTICS_VERSION, classify_failure, score_result


@pytest.mark.parametrize(
    ("resource", "threshold", "measured", "expected"),
    [
        ("cost", 0.0, 0.0, "Passed"),
        ("cost", 0.0, 0.01, "Cost Issue"),
        ("cost", None, 0.03, "Passed"),
        ("cost", None, 0.031, "Cost Issue"),
        ("cost", "omitted", 0.03, "Passed"),
        ("cost", "omitted", 0.031, "Cost Issue"),
        ("cost", 0.02, 0.02, "Passed"),
        ("cost", 0.02, 0.021, "Cost Issue"),
        ("latency", 0.0, 0.0, "Passed"),
        ("latency", 0.0, 1.0, "Latency Issue"),
        ("latency", None, 50.0, "Passed"),
        ("latency", None, 51.0, "Latency Issue"),
        ("latency", "omitted", 50.0, "Passed"),
        ("latency", "omitted", 51.0, "Latency Issue"),
        ("latency", 20.0, 20.0, "Passed"),
        ("latency", 20.0, 21.0, "Latency Issue"),
    ],
)
def test_resource_limits_preserve_zero_defaults_and_exact_boundaries(
    monkeypatch, resource, threshold, measured, expected
):
    monkeypatch.setattr(config, "COST_THRESHOLD_USD", 0.03)
    monkeypatch.setattr(config, "LATENCY_THRESHOLD_MS", 50)
    options = {}
    threshold_name = "cost_threshold_usd" if resource == "cost" else "latency_threshold_ms"
    if threshold != "omitted":
        options[threshold_name] = threshold

    result = classify_failure(
        answer_match=1.0,
        source_retrieval=1.0,
        citation=1.0,
        escalation=1.0,
        risk="low",
        actual_answer="Same supported answer.",
        expected_answer="Same supported answer.",
        latency_ms=measured if resource == "latency" else 0.0,
        estimated_cost=measured if resource == "cost" else 0.0,
        **options,
    )

    assert result == expected


@pytest.mark.parametrize(("latency", "cost", "expected"), [(0.0, 0.01, "Cost Issue"), (1.0, 0.0, "Latency Issue")])
def test_complete_answer_scoring_preserves_explicit_zero_limits(latency, cost, expected):
    answer = "Sample accounts stay active."
    result = score_result(
        actual_answer=answer,
        expected_answer=answer,
        expected_source="Sample policy",
        should_escalate=False,
        retrieved_chunks=[{"source_name": "Sample policy", "chunk_id": "policy", "chunk_text": answer}],
        provided_citations=[{"chunk_id": "policy"}],
        structured_escalation={"should_escalate": False},
        latency_ms=latency,
        estimated_cost=cost,
        latency_threshold_ms=0.0,
        cost_threshold_usd=0.0,
    )

    assert result["failure_type"] == expected


def test_calibration_from_before_zero_limit_fix_cannot_be_reused_as_current():
    thresholds = EvaluatorThresholdConfiguration()
    assert EVALUATOR_VERSION != "deterministic-v6"
    prior_result = {
        "status": "calibrated",
        "threshold_version": thresholds.version,
        "evaluator_version": "deterministic-v6",
        "label_semantics_version": LABEL_SEMANTICS_VERSION,
    }

    with pytest.raises(ValueError, match="evaluator version"):
        validate_calibration_for_run(
            prior_result,
            thresholds,
            evaluator_version=EVALUATOR_VERSION,
            label_semantics_version=LABEL_SEMANTICS_VERSION,
        )
