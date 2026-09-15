"""Configured attempts and unknown historical counts stay honest through reports."""

import json

import pandas as pd
import pytest

from src import database, evaluator
from src.aggregation import evaluate_candidate
from src.domain import ExecutionStatus, TargetResponse, TargetType
from src.presentation import execution_summary
from src.reporting import json_report
from src.storage import SQLiteRepository
from src.targets import ExternalHTTPTarget, ExternalTargetConfig, TargetAdapter
from src.ui_workflows import sample_review_workspace


class RetryFixture(TargetAdapter):
    target_type = TargetType.EXTERNAL_API

    def __init__(self, retries):
        self.retries = retries
        self.calls = 0

    @property
    def version(self):
        return f"fictional-retry-{self.retries}"

    @property
    def default_retry_count(self):
        return self.retries

    def execute(self, request):
        self.calls += 1
        if self.calls == 1:
            return TargetResponse(
                status=ExecutionStatus.RATE_LIMITED,
                http_status=429,
                error_code="fictional_rate_limit",
                metadata={"retryable": True},
            )
        return TargetResponse(status=ExecutionStatus.PASSED, answer=request["expected_answer"], latency_ms=1)


@pytest.mark.parametrize(("configured", "override", "calls"), [(0, None, 1), (2, None, 2), (2, 0, 1), (0, 1, 2)])
def test_evaluator_obeys_target_retry_default_or_explicit_override_and_persists_counts(
    monkeypatch, tmp_path, configured, override, calls
):
    base_engine = evaluator.ExecutionEngine

    class NoWaitEngine(base_engine):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, sleep=lambda _: None, **kwargs)

    monkeypatch.setattr(evaluator, "ExecutionEngine", NoWaitEngine)
    repository = SQLiteRepository(tmp_path / "attempts.sqlite3")
    context = repository.local_context()
    workspace = sample_review_workspace()
    adapter = RetryFixture(configured)
    with database.request_scope(repository, context):
        rows = evaluator.run_evaluation(
            pd.DataFrame(workspace["dataset"][:1]),
            workspace["sources"],
            {"Current": "Use only the provided sources."},
            "fictional-external-assistant",
            1,
            0.0,
            3500,
            0.03,
            "offline-test",
            target_adapter=adapter,
            max_retries=override,
            max_concurrency=1,
        )
    assert adapter.calls == calls
    row = rows.iloc[0]
    assert row["attempt_count"] == calls
    assert not row["cache_hit"]
    expected_retries = configured if override is None else override
    assert row["manifest"]["target"]["execution_policy"]["max_retries"] == expected_retries
    assert row["metadata"]["execution"]["attempt_count"] == calls
    stored = pd.DataFrame(repository.list_results(context))
    assert stored.iloc[0]["attempt_count"] == calls
    assert not stored.iloc[0]["cache_hit"]
    assert json.loads(json_report(stored))["metadata"]["execution_counts"]["retries"] == calls - 1


def test_unrecorded_attempts_are_unknown_instead_of_zero_retries():
    rows = pd.DataFrame(
        [{"case_id": "old-1", "execution_status": "passed", "failure_type": "Passed", "overall_score": 0.5}]
    )
    counts = execution_summary(rows)
    assert counts["retries"] is None
    assert counts["attempt_counts_unknown"] == 1
    assert evaluate_candidate(rows)["counts"]["retry_count"] is None
    rows["attempt_count"] = 3
    assert execution_summary(rows)["retries"] == 2
    rows.loc[1] = {"case_id": "unknown-2", "execution_status": "passed", "failure_type": "Passed"}
    counts = execution_summary(rows)
    assert counts["retries"] is None and counts["observed_retries"] == 2


def test_cached_and_cancelled_zero_attempts_do_not_create_negative_retry_counts():
    rows = pd.DataFrame(
        [
            {"case_id": "cached", "attempt_count": 0, "cache_hit": True, "execution_status": "passed"},
            {"case_id": "cancelled", "attempt_count": 0, "execution_status": "cancelled"},
            {"case_id": "retried", "attempt_count": 2, "execution_status": "passed"},
        ]
    )
    assert execution_summary(rows)["retries"] == 1


@pytest.mark.parametrize(
    ("method", "template", "expected"),
    [
        ("POST", {"input": "${question}"}, False),
        ("POST", {"${system_prompt}": "constant"}, False),
        ("GET", {"prompt": "${system_prompt}"}, False),
        ("POST", {"messages": [{"content": "Instructions: ${system_prompt}"}]}, True),
    ],
)
def test_only_rendered_external_body_values_count_as_sending_system_prompt(method, template, expected):
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="Fictional", endpoint="https://assistant.example.test/chat", method=method, request_template=template
        )
    )
    assert target.sends_system_prompt is expected


def test_external_prompt_comparison_is_rejected_before_any_request_when_prompt_is_not_sent(tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("No endpoint request should be made")

    target = ExternalHTTPTarget(
        ExternalTargetConfig(name="Fictional", endpoint="https://assistant.example.test/chat"), opener=forbidden
    )
    repository = SQLiteRepository(tmp_path / "prompt-scope.sqlite3")
    context = repository.local_context()
    sample = sample_review_workspace()
    with database.request_scope(repository, context), pytest.raises(ValueError, match="does not send"):
        evaluator.run_evaluation(
            pd.DataFrame(sample["dataset"][:1]),
            sample["sources"],
            {"Before": "A", "After": "B"},
            "external-assistant",
            1,
            0.0,
            3500,
            0.03,
            "comparison",
            target_adapter=target,
            max_concurrency=1,
        )
    assert repository.list_runs(context) == []
