import json

import pandas as pd
import pytest

from src.aggregation import LaunchGateConfig
from src.reporting import csv_report, html_report, json_report


@pytest.mark.parametrize("report", [json_report, html_report, csv_report])
def test_candidate_and_metadata_content_is_redacted_everywhere(report):
    frame = pd.DataFrame(
        [
            {
                "case_id": "case-1",
                "execution_status": "passed",
                "failure_type": "Passed",
                "candidate_name": "person@example.com secret://PRIVATE_TOKEN",
                "prompt_name": "person@example.com",
                "prompt_version": "p1",
                "target_type": "synthetic_mock",
                "model_name": "mock-model",
                "target_version": "t1",
                "actual_answer": "hello person@example.com",
                "metadata": {"person@example.com": "secret://PRIVATE_TOKEN"},
            }
        ]
    )
    output = report(frame)
    assert "person@example.com" not in output
    assert "secret://PRIVATE_TOKEN" not in output
    assert "synthetic" in output.lower()


def test_reports_expose_missing_measurement_counts_without_zero_attribution():
    frame = pd.DataFrame(
        [
            {
                "case_id": "case-1",
                "execution_status": "passed",
                "failure_type": "Passed",
                "target_type": "external_api",
                "overall_score": 0.5,
            }
        ]
    )
    report = json.loads(json_report(frame))
    result = next(iter(report["candidates"].values()))
    assert result["metrics"]["total_cost_usd"] is None
    assert result["metrics"]["cost_measurement_count"] == 0


@pytest.mark.parametrize("report", [json_report, csv_report, html_report])
def test_custom_gate_labels_do_not_bypass_report_redaction(report):
    frame = pd.DataFrame(
        [
            {
                "case_id": "one",
                "target_type": "foundation_model",
                "execution_status": "passed",
                "failure_type": "Passed",
                "overall_score": 0.5,
            }
        ]
    )
    gates = LaunchGateConfig(required_categories=("person@example.com", "secret://PRIVATE_TOKEN"))
    output = report(frame, gates=gates)
    assert "person@example.com" not in output
    assert "secret://PRIVATE_TOKEN" not in output
