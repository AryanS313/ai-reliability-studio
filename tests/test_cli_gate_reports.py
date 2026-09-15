"""Offline CLI boundary tests: exit status and report assess one configured policy."""

from __future__ import annotations

import json
from dataclasses import asdict
from io import StringIO

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from src import cli
from src.aggregation import LaunchGateConfig
from src.versioning import version_hash


def _successful_observations():
    return pd.DataFrame(
        [
            {
                "case_id": f"case-{number}",
                "question": f"Policy question {number}",
                "prompt_name": "Baseline",
                "prompt_version": "prompt-v1",
                "target_version": "target-v1",
                "target_type": "foundation_model",
                "model_name": "offline-fixture",
                "execution_status": "passed",
                "failure_type": "Passed",
                "failure_labels": [],
                "overall_score": 0.85,
                "groundedness_score": 0.9,
                "citation_correctness_score": 0.9,
                "escalation_correctness_score": 0.9,
                "dataset_launch_eligible": True,
                "calibration_status": "calibrated",
                "category": "Policy",
            }
            for number in range(35)
        ]
    )


def _arguments(tmp_path, gate_content, report_format):
    document = tmp_path / "policy.md"
    document.write_text("Refunds require a transaction ID.")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Use the supplied policy.")
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "question": "Refund requirements?",
                "expected_answer": "A transaction ID.",
                "expected_source": "Policy",
                "category": "Policy",
                "should_escalate": False,
            }
        )
        + "\n"
    )
    gate_path = tmp_path / "gates.json"
    gate_path.write_text(gate_content)
    report_path = tmp_path / f"report.{report_format}"
    database_path = tmp_path / "gate-run.sqlite3"
    return (
        [
            "run",
            "--dataset",
            str(dataset),
            "--document",
            str(document),
            "--prompt",
            str(prompt),
            "--gate-config",
            str(gate_path),
            "--database",
            str(database_path),
            "--format",
            report_format,
            "--output",
            str(report_path),
        ],
        report_path,
        database_path,
    )


def _read_gate_evidence(path, report_format):
    if report_format == "json":
        payload = json.loads(path.read_text())
        assessment = next(iter(payload["candidates"].values()))
        manifest = payload["metadata"]["report_gate_manifest"]
        return manifest["configuration"], manifest["version"], assessment["verdict"], assessment["gate_results"]
    if report_format == "csv":
        rows = pd.read_csv(path)
        assert rows["report_gate_configuration_version"].nunique() == 1
        row = rows.iloc[0]
        return (
            json.loads(row["report_gate_configuration"]),
            row["report_gate_configuration_version"],
            row["report_candidate_verdict"],
            json.loads(row["report_candidate_gate_results"]),
        )
    # Human-readable HTML retains exact policy in escaped, non-executable metadata.
    soup = BeautifulSoup(path.read_text(), "html.parser")
    payload = json.loads(soup.find("script", id="report-evidence").string)
    manifest = payload["metadata"]["report_gate_manifest"]
    assessment = next(iter(payload["candidates"].values()))
    return manifest["configuration"], manifest["version"], assessment["verdict"], assessment["gate_results"]


@pytest.mark.parametrize("report_format", ["json", "csv", "html"])
@pytest.mark.parametrize(
    ("threshold", "exit_code", "verdict"),
    [(0.8, cli.EXIT_SUCCESS, "Ready for Internal Testing"), (0.9, cli.EXIT_GATE_FAILURE, "Needs Improvement")],
)
def test_cli_report_and_exit_use_the_same_configured_gates(
    tmp_path, monkeypatch, report_format, threshold, exit_code, verdict
):
    arguments, path, _ = _arguments(tmp_path, json.dumps({"minimum_overall_quality": threshold}), report_format)
    monkeypatch.setattr(cli, "run_evaluation", lambda *args, **kwargs: _successful_observations())
    assert cli.main(arguments) == exit_code
    configuration, version, observed_verdict, checks = _read_gate_evidence(path, report_format)
    expected_configuration = asdict(LaunchGateConfig(minimum_overall_quality=threshold))
    assert configuration["minimum_overall_quality"] == threshold
    assert configuration["require_calibration"] is True
    assert configuration["maximum_severe_safety_failures"] == 0
    assert version == version_hash(expected_configuration)
    assert observed_verdict == verdict
    overall = next(check for check in checks if check["name"] == "minimum_overall_quality")
    assert overall["threshold"] == threshold
    assert overall["passed"] is (threshold == 0.8)
    if report_format == "html":
        tables = pd.read_html(StringIO(path.read_text()))
        checks_table = next(table for table in tables if "Check" in table.columns)
        visible_overall = checks_table.set_index("Check").loc["Overall answer quality"]
        assert f"requires at least {threshold:.0%}" in visible_overall["What it means"]
        assert visible_overall["Result"] == ("Met" if threshold == 0.8 else "Not met")


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "[]",
        '{"unknown":1}',
        '{"minimum_overall_quality":"0.8"}',
        '{"minimum_overall_quality":NaN}',
        '{"minimum_sample_size":0}',
        '{"require_calibration":"false"}',
        '{"required_categories":"Policy"}',
    ],
)
def test_invalid_gate_config_is_rejected_before_execution_or_storage(tmp_path, monkeypatch, content):
    arguments, report, database_path = _arguments(tmp_path, content, "json")
    monkeypatch.setattr(
        cli, "run_evaluation", lambda *args, **kwargs: pytest.fail("Invalid gates must prevent execution")
    )
    assert cli.main(arguments) == cli.EXIT_CONFIGURATION_ERROR
    assert not report.exists()
    assert not database_path.exists()


@pytest.mark.parametrize("report_format", ["json", "csv", "html"])
def test_report_keeps_critical_and_calibration_gates_with_permissive_quality(tmp_path, monkeypatch, report_format):
    arguments, path, _ = _arguments(tmp_path, '{"minimum_overall_quality":0.1}', report_format)
    observations = _successful_observations()
    observations.loc[0, "calibration_status"] = "insufficiently_calibrated"
    observations.at[0, "failure_labels"] = ["privacy_violation"]
    monkeypatch.setattr(cli, "run_evaluation", lambda *args, **kwargs: observations)
    assert cli.main(arguments) == cli.EXIT_GATE_FAILURE
    _, _, verdict, checks = _read_gate_evidence(path, report_format)
    assert verdict == "Not Ready"
    failed = {check["name"] for check in checks if not check["passed"]}
    assert {"maximum_severe_safety_failures", "minimum_evaluator_calibration"} <= failed
    if report_format == "html":
        tables = pd.read_html(StringIO(path.read_text()))
        checks_table = next(table for table in tables if "Check" in table.columns).set_index("Check")
        assert checks_table.loc["Critical safety failures", "Result"] == "Not met"
        assert checks_table.loc["Evaluator checked against human reviews", "Result"] == "Not met"
