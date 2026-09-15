from __future__ import annotations

import json

from src import cli


def cli_inputs(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "question": "What is required for a refund?",
                "expected_answer": "Refunds require a transaction ID.",
                "expected_source": "Policy",
                "category": "Refund",
                "should_escalate": False,
            }
        )
        + "\n"
    )
    document = tmp_path / "policy.md"
    document.write_text("Refunds require a transaction ID.")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Answer using the supplied policy.")
    output = tmp_path / "report.json"
    arguments = [
        "run",
        "--dataset",
        str(dataset),
        "--document",
        str(document),
        "--prompt",
        str(prompt),
        "--database",
        str(tmp_path / "run.sqlite3"),
        "--output",
        str(output),
    ]
    return arguments, output


def test_missing_provider_key_returns_execution_error_and_inspectable_report(tmp_path, monkeypatch):
    arguments, output = cli_inputs(tmp_path)
    monkeypatch.delenv("ARS_TEST_MISSING_KEY", raising=False)
    monkeypatch.delenv("session_openai_key", raising=False)
    status = cli.main([*arguments, "--model", "gpt-4o-mini", "--api-key-env", "ARS_TEST_MISSING_KEY"])
    assert status == cli.EXIT_EXECUTION_ERROR
    report = json.loads(output.read_text())
    assert report["metadata"]["execution_counts"]["quality_scored_executions"] == 0
    assert report["executions"][0]["execution_status"] == "invalid_response"
    assert report["executions"][0]["error_code"] == "target_configuration_error"
    assert all(item["launch_blocked"] for item in report["candidates"].values())


def test_completed_synthetic_run_still_returns_gate_failure(tmp_path):
    arguments, output = cli_inputs(tmp_path)
    status = cli.main([*arguments, "--model", "mock-model"])
    assert status == cli.EXIT_GATE_FAILURE
    report = json.loads(output.read_text())
    assert report["metadata"]["execution_counts"]["infrastructure_errors"] == 0
    assert all(
        item["verdict"] == "Synthetic demonstration — no launch verdict" for item in report["candidates"].values()
    )


def test_synthetic_failure_fixture_preserves_documented_ci_gate_exit(tmp_path):
    arguments, output = cli_inputs(tmp_path)
    dataset = tmp_path / "cases.jsonl"
    row = json.loads(dataset.read_text())
    row["mock_scenario"] = "malformed_response"
    dataset.write_text(json.dumps(row) + "\n")
    status = cli.main([*arguments, "--model", "mock-model"])
    assert status == cli.EXIT_GATE_FAILURE
    report = json.loads(output.read_text())
    assert report["metadata"]["execution_counts"]["infrastructure_errors"] == 1
    assert report["metadata"]["execution_counts"]["quality_scored_executions"] == 0
