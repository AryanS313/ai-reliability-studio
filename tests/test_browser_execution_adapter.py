"""Offline scheduling/recovery checks; these fixtures never call a real assistant."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from browser_runtime import browser_execution as browser
from src import config, execution, hosted_limits
from src.domain import ExecutionStatus, TargetResponse, TargetType
from src.targets import TargetAdapter, TargetConfigurationError


class ScriptedTarget(TargetAdapter):
    target_type = TargetType.EXTERNAL_API

    def __init__(self, responses=(), *, retries=0):
        self.responses = iter(responses)
        self.calls = []
        self.retries = retries

    @property
    def version(self):
        return "offline-browser-adapter-fixture"

    @property
    def default_retry_count(self):
        return self.retries

    def execute(self, request):
        self.calls.append(request["case_id"])
        response = next(self.responses, TargetResponse(status=ExecutionStatus.PASSED, answer="Fictional answer."))
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def emscripten(monkeypatch):
    # Only platform routing is simulated. Real Stlite behavior is a separate
    # browser acceptance check, and no native network calls are permitted here.
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setattr(execution, "ExecutionEngine", execution.ExecutionEngine)
    monkeypatch.setattr(execution, "ThreadPoolExecutor", execution.ThreadPoolExecutor)
    evaluator = sys.modules.get("src.evaluator")
    if evaluator is not None:
        monkeypatch.setattr(evaluator, "ExecutionEngine", evaluator.ExecutionEngine)

    def no_network(*args, **kwargs):
        raise AssertionError("Browser execution adapter tests must stay offline")

    monkeypatch.setattr("socket.getaddrinfo", no_network)
    monkeypatch.setattr("socket.socket.connect", no_network)


def requests(*case_ids):
    return [
        {"case_id": case_id, "question": "Fictional question", "dataset_version": "fixture-cases"}
        for case_id in case_ids
    ]


def terminal(target, request):
    return execution.ExecutionRecord(
        execution_key=execution.execution_cache_key(request, target.version),
        case_id=request["case_id"],
        status=ExecutionStatus.PASSED,
        response=TargetResponse(status=ExecutionStatus.PASSED, answer="Previously completed fictional answer."),
        completed_at=1.0,
        attempt_count=1,
    )


def test_native_platform_does_not_install_and_cannot_construct_browser_engine(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    native, pool = execution.ExecutionEngine, execution.ThreadPoolExecutor
    assert browser.install_browser_execution() == {"installed": False, "reason": "native_runtime_unchanged"}
    assert execution.ExecutionEngine is native
    assert execution.ThreadPoolExecutor is pool
    with pytest.raises(RuntimeError, match="only for Emscripten"):
        browser.BrowserSequentialExecutionEngine(ScriptedTarget())


def test_browser_mode_does_not_require_native_hosted_admission(emscripten, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "browser")
    assert not config.hosted_sessions_enabled()
    assert execution.ExecutionPolicy().max_retries == 2
    # Browser admission remains the adapter's bounded sequential policy; a
    # server-side budget must neither be required nor created on this path.
    hosted_limits.validate_execution_limits(101, 1, 2)
    target = ScriptedTarget()
    engine = browser.BrowserSequentialExecutionEngine(target)
    records = hosted_limits.guard_run(engine.run)(requests("browser-custom"))
    assert records[0].status == ExecutionStatus.PASSED
    assert engine.policy.max_concurrency == 1
    assert hosted_limits.current_session() is None


def test_browser_entry_sets_mode_before_importing_execution_adapter():
    # Run the real entry script in an isolated interpreter. Stub the two browser
    # installers and app launch, retaining its actual environment/import order.
    script = r"""
import os, runpy, sys, types
assert 'src.config' not in sys.modules
def install():
    from src import config, execution
    assert config.APP_ACCESS_MODE == 'browser'
    assert not config.hosted_sessions_enabled()
    assert execution.ExecutionPolicy().max_retries == 2
    assert not any(config.PROVIDER_API_KEYS.values())
sys.modules['browser_execution'] = types.SimpleNamespace(install_browser_execution=install)
sys.modules['browser_transport'] = types.SimpleNamespace(install_browser_provider_clients=lambda: None)
entry = open('browser_runtime/entry.py').read()
runpy.run_path = lambda *args, **kwargs: None
exec(compile(entry, 'browser_runtime/entry.py', 'exec'), {'__name__': '__main__'})
"""
    environment = {**os.environ, "APP_ACCESS_MODE": "hosted-session", "STUDIO_EXTRACTION_WORKER": "1"}
    result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "3"])
def test_browser_case_limit_requires_a_positive_integer(emscripten, limit):
    with pytest.raises(ValueError, match="positive integer"):
        browser.BrowserSequentialExecutionEngine(ScriptedTarget(), case_limit=limit)


def test_concurrency_is_explicit_and_native_request_logic_is_inherited(emscripten):
    with pytest.raises(ValueError, match="max_concurrency=1"):
        browser.BrowserSequentialExecutionEngine(ScriptedTarget(), execution.ExecutionPolicy(max_concurrency=2))
    engine = browser.BrowserSequentialExecutionEngine(ScriptedTarget(retries=3))
    assert engine.policy.max_concurrency == 1
    assert engine.policy.max_retries == 3
    assert browser.BrowserSequentialExecutionEngine._execute_one is browser._NativeEngine._execute_one
    assert browser.BrowserSequentialExecutionEngine._save_checkpoint is browser._NativeEngine._save_checkpoint


def test_oversize_iterable_is_bounded_and_rejected_before_any_call_or_checkpoint(emscripten):
    consumed, checkpoints = [], []

    def infinite_requests():
        index = 0
        while True:
            consumed.append(index)
            yield requests(str(index))[0]
            index += 1

    target = ScriptedTarget()
    engine = browser.BrowserSequentialExecutionEngine(target, case_limit=2, checkpoint=checkpoints.append)
    with pytest.raises(browser.BrowserRunLimitError, match="2-case limit"):
        engine.run(infinite_requests())
    assert consumed == [0, 1, 2]
    assert target.calls == checkpoints == []
    assert engine.last_records == ()


def test_invalid_request_rejected_before_earlier_valid_request_executes(emscripten):
    target = ScriptedTarget()
    engine = browser.BrowserSequentialExecutionEngine(target)
    with pytest.raises(ValueError, match="must be an object"):
        engine.run([*requests("valid"), "not-an-object"])
    assert not target.calls
    assert engine.last_records == ()


def test_cancellation_before_run_checkpoints_every_case_without_target_calls(emscripten):
    token = execution.CancellationToken()
    token.cancel()
    target = ScriptedTarget()
    checkpoints, progress = [], []
    engine = browser.BrowserSequentialExecutionEngine(
        target, checkpoint=lambda record: checkpoints.append(record.to_dict())
    )
    records = engine.run(
        requests("first", "second"),
        cancellation=token,
        progress=lambda done, total, record: progress.append((done, total, record.case_id)),
    )
    assert not target.calls
    assert all(record.status == ExecutionStatus.CANCELLED for record in records)
    assert all(record.attempt_count == 0 and record.completed_at is not None for record in records)
    assert [item["status"] for item in checkpoints] == ["cancelled", "cancelled"]
    assert progress == [(1, 2, "first"), (2, 2, "second")]


def test_cancellation_after_first_answer_keeps_answer_and_cancels_remaining_cases(emscripten):
    token = execution.CancellationToken()
    target = ScriptedTarget()
    engine = browser.BrowserSequentialExecutionEngine(target)

    def progress(done, total, record):
        if done == 1:
            token.cancel()

    records = engine.run(requests("first", "second", "third"), cancellation=token, progress=progress)
    assert target.calls == ["first"]
    assert [record.status for record in records] == [
        ExecutionStatus.PASSED,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.CANCELLED,
    ]
    assert records[0].response.answer == "Fictional answer."


@pytest.mark.parametrize("status", [ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT, ExecutionStatus.RATE_LIMITED])
def test_retries_preserve_attempt_counts_checkpoint_order_and_backoff(emscripten, status):
    target = ScriptedTarget([TargetResponse(status=status)], retries=1)
    sleeps, checkpoints = [], []
    engine = browser.BrowserSequentialExecutionEngine(
        target, sleep=sleeps.append, checkpoint=lambda record: checkpoints.append(record.to_dict())
    )
    record = engine.run(requests("retry"))[0]
    assert target.calls == ["retry", "retry"]
    assert record.status == ExecutionStatus.PASSED
    assert record.attempt_count == 2
    assert sleeps == [0.5]
    assert checkpoints[0]["status"] == "running"
    assert checkpoints[1]["status"] == status.value
    assert checkpoints[-1]["status"] == "passed"
    assert checkpoints[-1]["completed_at"] is not None


@pytest.mark.parametrize("http_status", [400, 401, 403, 404, 422])
def test_nontransient_client_errors_do_not_retry(emscripten, http_status):
    target = ScriptedTarget([TargetResponse(status=ExecutionStatus.FAILED, http_status=http_status)], retries=3)
    sleeps = []
    record = browser.BrowserSequentialExecutionEngine(target, sleep=sleeps.append).run(requests("invalid"))[0]
    assert target.calls == ["invalid"]
    assert record.attempt_count == 1 and record.status == ExecutionStatus.FAILED
    assert "retry_skipped" in record.metadata
    assert not sleeps


@pytest.mark.parametrize(
    ("metadata", "expected_attempts", "expected_sleeps"),
    [({"retryable": False}, 1, []), ({"retry_after_seconds": 2}, 2, [2]), ({"retry_after_seconds": 11}, 1, [])],
)
def test_retry_metadata_and_bounded_retry_after_remain_authoritative(
    emscripten, metadata, expected_attempts, expected_sleeps
):
    target = ScriptedTarget(
        [TargetResponse(status=ExecutionStatus.RATE_LIMITED, http_status=429, metadata=metadata)], retries=2
    )
    sleeps = []
    record = browser.BrowserSequentialExecutionEngine(target, sleep=sleeps.append).run(requests("limited"))[0]
    assert len(target.calls) == record.attempt_count == expected_attempts
    assert sleeps == expected_sleeps
    if metadata.get("retry_after_seconds") == 11:
        assert record.metadata["retry_suppressed"] == "retry_after_exceeds_wait_limit"


def test_cancellation_during_backoff_prevents_retry_and_next_case(emscripten):
    token = execution.CancellationToken()
    target = ScriptedTarget([TargetResponse(status=ExecutionStatus.RATE_LIMITED)], retries=2)
    engine = browser.BrowserSequentialExecutionEngine(target, sleep=lambda _: token.cancel())
    records = engine.run(requests("first", "second"), cancellation=token)
    assert target.calls == ["first"]
    assert all(record.status == ExecutionStatus.CANCELLED for record in records)
    assert [record.attempt_count for record in records] == [1, 0]


def test_duplicate_requests_are_reported_cancelled_without_extra_calls(emscripten):
    target = ScriptedTarget()
    engine = browser.BrowserSequentialExecutionEngine(target)
    progress = []
    records = engine.run(
        requests("same", "same", "other"),
        progress=lambda done, total, record: progress.append((done, total, record.case_id)),
    )
    assert target.calls == ["same", "other"]
    assert records[1].status == ExecutionStatus.CANCELLED
    assert records[1].metadata["duplicate_prevented"] is True
    assert records[1].attempt_count == 0
    assert [done for done, _, _ in progress] == [1, 2, 3]
    assert engine.run(requests("same"))[0].metadata["duplicate_prevented"] is True
    assert target.calls == ["same", "other"]


def test_interleaved_reused_records_keep_input_order_and_each_progress_event(emscripten):
    target = ScriptedTarget()
    batch = requests("pending-first", "reused-second", "pending-third", "reused-fourth")
    reused = [terminal(target, batch[index]) for index in (1, 3)]
    progress = []
    records = browser.BrowserSequentialExecutionEngine(target).run(
        batch,
        completed={record.execution_key: record for record in reused},
        progress=lambda done, total, record: progress.append((done, total, record.case_id)),
    )
    assert [record.case_id for record in records] == [request["case_id"] for request in batch]
    assert records[1] is reused[0] and records[3] is reused[1]
    assert target.calls == ["pending-first", "pending-third"]
    assert progress == [
        (1, 4, "reused-second"),
        (2, 4, "reused-fourth"),
        (3, 4, "pending-first"),
        (4, 4, "pending-third"),
    ]


def test_shared_cache_reuses_only_success_and_records_zero_new_attempts(emscripten):
    target = ScriptedTarget()
    cache = execution.ExecutionCache()
    first = browser.BrowserSequentialExecutionEngine(target, cache=cache).run(requests("cached"))[0]
    checkpoints = []
    second = browser.BrowserSequentialExecutionEngine(target, cache=cache, checkpoint=checkpoints.append).run(
        requests("cached")
    )[0]
    assert target.calls == ["cached"]
    assert second.cache_hit is True and second.attempt_count == 0
    assert second.response is first.response
    assert checkpoints == [second]
    failed_request = requests("failed")[0]
    cache.set(
        execution.execution_cache_key(failed_request, target.version), TargetResponse(status=ExecutionStatus.FAILED)
    )
    browser.BrowserSequentialExecutionEngine(target, cache=cache).run([failed_request])
    assert target.calls == ["cached", "failed"]


def test_progress_failure_keeps_completed_record_and_unstarted_records(emscripten):
    target = ScriptedTarget()
    engine = browser.BrowserSequentialExecutionEngine(target)

    def bad_progress(*args):
        raise RuntimeError("fictional-sensitive-callback-value")

    with pytest.raises(browser.BrowserRunAborted) as caught:
        engine.run(requests("first", "second"), progress=bad_progress)
    error = caught.value
    assert error.records == engine.last_records
    assert len(error.completed_records) == 1
    assert error.completed_records[0].response.answer == "Fictional answer."
    assert error.records[1].status == ExecutionStatus.PENDING
    assert target.calls == ["first"]
    assert "fictional-sensitive" not in str(error)
    assert "not guaranteed saved" in str(error)


@pytest.mark.parametrize("when", ["before_call", "after_response", "after_completion"])
def test_checkpoint_failure_preserves_returned_responses_without_claiming_saved(emscripten, when):
    target = ScriptedTarget()

    def bad_checkpoint(record):
        fail = (
            record.status == ExecutionStatus.RUNNING
            if when == "before_call"
            else record.status == ExecutionStatus.PASSED
            and (when == "after_response" or record.completed_at is not None)
        )
        if fail:
            raise RuntimeError("fictional-sensitive-checkpoint-value")

    engine = browser.BrowserSequentialExecutionEngine(target, checkpoint=bad_checkpoint)
    with pytest.raises(browser.BrowserRunAborted) as caught:
        engine.run(requests("first", "second"))
    error = caught.value
    assert error.records == engine.last_records
    assert "fictional-sensitive" not in str(error)
    assert error.records[1].status == ExecutionStatus.PENDING
    assert len(error.completed_records) == (0 if when == "before_call" else 1)
    if when == "after_response":
        assert error.completed_records[0].response.answer == "Fictional answer."
        assert error.completed_records[0].metadata["checkpoint_persistence"] == "unconfirmed"
        assert error.completed_records[0].metadata["completion_recovered_after_abort"] is True
    assert target.calls == ([] if when == "before_call" else ["first"])


def test_callback_failure_on_reused_record_preserves_it_without_starting_pending_case(emscripten):
    target = ScriptedTarget()
    batch = requests("pending", "saved")
    saved = terminal(target, batch[1])

    def bad_progress(*args):
        raise RuntimeError("fixture callback failed")

    with pytest.raises(browser.BrowserRunAborted) as caught:
        browser.BrowserSequentialExecutionEngine(target).run(
            batch, completed={saved.execution_key: saved}, progress=bad_progress
        )
    assert caught.value.completed_records == (saved,)
    assert caught.value.records[0].status == ExecutionStatus.PENDING
    assert not target.calls


def test_configuration_errors_stay_unscored_nonretryable_and_redacted(emscripten):
    target = ScriptedTarget([TargetConfigurationError("fixture credential must not be shown")], retries=3)
    record = browser.BrowserSequentialExecutionEngine(target).run(requests("bad-config"))[0]
    assert record.status == ExecutionStatus.INVALID_RESPONSE
    assert record.attempt_count == 1
    assert record.response.metadata["quality_score_eligible"] is False
    assert "fixture credential" not in record.response.safe_error


def test_hash_guard_rejects_unreviewed_source_without_mutating_runtime(emscripten, monkeypatch):
    native, pool = execution.ExecutionEngine, execution.ThreadPoolExecutor
    monkeypatch.setattr(browser, "EXECUTION_SOURCE_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="execution module changed"):
        browser.install_browser_execution()
    assert execution.ExecutionEngine is native and execution.ThreadPoolExecutor is pool


def test_actual_reviewed_source_hash_installs_adapter_and_blocks_native_threads(emscripten, monkeypatch):
    from src import evaluator

    monkeypatch.setattr(evaluator, "ExecutionEngine", evaluator.ExecutionEngine)
    actual = hashlib.sha256(Path(execution.__file__).read_bytes()).hexdigest()
    assert browser.EXECUTION_SOURCE_SHA256 == actual
    installed = browser.install_browser_execution()
    assert installed["installed"] is True
    assert installed["source_sha256"] == actual
    assert installed["effective_concurrency"] == 1
    assert installed["native_execution_threads"] is False
    assert execution.ExecutionEngine is browser.BrowserSequentialExecutionEngine
    assert evaluator.ExecutionEngine is browser.BrowserSequentialExecutionEngine
    target = ScriptedTarget()
    with pytest.raises(browser.NativeThreadsUnavailable):
        browser._NativeEngine(target).run(requests("forbidden"))
    assert not target.calls
    assert execution.ExecutionEngine(target).run(requests("allowed"))[0].status == ExecutionStatus.PASSED
