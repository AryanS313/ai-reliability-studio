from __future__ import annotations

import math

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src import charts


def _evidence() -> pd.DataFrame:
    rows = []
    for index, (prompt, model, cost) in enumerate(
        [("Current Prompt", "known-model", 0.02), ("Improved Prompt", None, None)]
    ):
        rows.append(
            {
                "case_id": f"case-{index}",
                "question": f"Question {index}",
                "prompt_name": prompt,
                "prompt_version": str(index) * 64,
                "model_name": model,
                "target_type": "synthetic_mock",
                "target_version": "target-version",
                "execution_status": "passed",
                "category": "policy-exception",
                "failure_type": "ExpectedAnswerMismatch" if index else "Passed",
                "hallucination_risk": "Low",
                "overall_score": 0.7 + index / 10,
                "expected_answer_match_score": 0.8,
                "source_retrieval_score": 0.9,
                "citation_correctness_score": 0.8,
                "groundedness_score": 0.8,
                "escalation_correctness_score": 1.0,
                "latency_ms": 150.0,
                "estimated_cost": cost,
            }
        )
    return pd.DataFrame(rows)


def test_metric_table_keeps_unreported_model_and_unknown_cost_without_mutating_evidence():
    evidence = _evidence()
    original = evidence.copy(deep=True)
    table = charts.prompt_metric_table(evidence)
    assert set(table["prompt_name"]) == {"Current Prompt", "Improved Prompt"}
    candidate = table.loc[table["prompt_name"].eq("Improved Prompt")].iloc[0]
    assert pd.isna(candidate["model_name"])
    assert pd.isna(candidate["estimated_cost"])
    assert table.loc[table["prompt_name"].eq("Current Prompt"), "estimated_cost"].iloc[0] == 0.02
    assert_frame_equal(evidence, original)


@pytest.mark.parametrize("builder", [charts.model_comparison_chart, charts.latency_chart, charts.cost_chart])
def test_model_charts_retain_unreported_model_groups(builder):
    figure = builder(_evidence())
    labels = {str(value) for trace in figure.data for value in trace.x}
    labels.update(trace.name for trace in figure.data)
    assert "Model not reported" in labels
    assert sum(len(trace.x) for trace in figure.data) == 2


def test_cost_display_distinguishes_missing_measurements_from_zero():
    evidence = _evidence()
    assert math.isnan(charts.metric_summary(evidence)["total_cost"])
    figure = charts.cost_chart(evidence)
    missing = next(trace for trace in figure.data if trace.name == "Model not reported")
    assert all(pd.isna(value) for value in missing.y)
    assert any("Cost not reported for 1 of 2 checks" in item.text for item in figure.layout.annotations)
    complete = evidence.assign(estimated_cost=[0.02, 0.0])
    assert charts.metric_summary(complete)["total_cost"] == 0.02
    assert not charts.cost_chart(complete).layout.annotations


def test_known_cost_includes_failed_call_observations():
    evidence = _evidence().assign(estimated_cost=[0.02, 0.01], execution_status=["passed", "timeout"])
    assert charts.metric_summary(evidence)["total_cost"] == pytest.approx(0.03)


@pytest.mark.parametrize(
    "builder",
    [
        charts.prompt_comparison_chart,
        charts.model_comparison_chart,
        charts.category_score_chart,
        charts.failure_distribution_chart,
        charts.hallucination_distribution_chart,
        charts.latency_chart,
        charts.cost_chart,
    ],
)
def test_chart_text_uses_readable_labels_and_does_not_claim_candidate_improvement(builder):
    evidence = _evidence()
    original = evidence.copy(deep=True)
    figure = builder(evidence)
    visible_text = " ".join(
        [str(figure.layout.title.text), str(figure.layout.xaxis.title.text), str(figure.layout.yaxis.title.text)]
        + [str(figure.layout.legend.title.text)]
        + [str(trace.hovertemplate) for trace in figure.data]
        + [str(trace.name) for trace in figure.data]
        + [str(value) for trace in figure.data if getattr(trace, "labels", None) is not None for value in trace.labels]
    )
    for raw in ["prompt_name", "overall_score", "failure_type", "estimated_cost", "Improved Prompt"]:
        assert raw not in visible_text
    assert_frame_equal(evidence, original)


def test_opaque_instruction_names_are_distinct_readable_groups_without_hashes():
    evidence = _evidence().assign(prompt_name=["a" * 64, "b" * 64])
    figure = charts.prompt_comparison_chart(evidence)
    labels = list(figure.data[0].x)
    assert labels == ["Saved instructions", "Saved instructions (2)"]
    assert list(figure.data[0].y) == pytest.approx([70, 80])
    assert evidence["prompt_name"].tolist() == ["a" * 64, "b" * 64]


def test_display_alias_collision_does_not_merge_saved_instruction_groups():
    evidence = _evidence().assign(prompt_name=["Improved Prompt", "Candidate Prompt"])
    figure = charts.prompt_comparison_chart(evidence)
    assert len(set(figure.data[0].x)) == 2
    assert sorted(figure.data[0].y) == pytest.approx([70, 80])


def test_metric_table_attaches_verdict_to_its_own_candidate_when_version_order_differs():
    evidence = _evidence().assign(
        target_type="foundation_model",
        prompt_version=["f" * 64, "0" * 64],
        failure_labels=[["privacy_violation"], []],
        calibration_status="insufficiently_calibrated",
    )
    table = charts.prompt_metric_table(evidence).set_index("prompt_name")
    assert table.loc["Current Prompt", "verdict"] == "Not Ready"
    assert table.loc["Improved Prompt", "verdict"] == "Insufficient Evidence"


def test_metric_table_does_not_assign_one_verdict_to_a_group_of_distinct_saved_revisions():
    evidence = _evidence().assign(prompt_name="Current Prompt", model_name="known-model")
    table = charts.prompt_metric_table(evidence)
    assert len(table) == 1
    assert table.iloc[0]["verdict"] == "Multiple saved revisions; inspect each release check"
