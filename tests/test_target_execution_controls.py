from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from io import BytesIO
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from src import config
from src.domain import ExecutionStatus
from src.execution import ExecutionEngine, ExecutionPolicy
from src.targets import (
    ExternalHTTPTarget,
    ExternalTargetConfig,
    FoundationModelConfig,
    FoundationModelTarget,
    TargetConfigurationError,
)
from src.versioning import version_hash

ENDPOINT = "https://assistant.example.test/chat"


def test_foundation_target_version_tracks_system_instruction_transport(monkeypatch):
    configuration = FoundationModelConfig("anthropic", "claude-sonnet-5", "secret://session/anthropic")
    target = FoundationModelTarget(configuration)
    version = target.version
    assert target.implementation_version == "provider-native-system-v2"
    assert version != version_hash({"type": target.target_type.value, **configuration.__dict__})
    assert version == FoundationModelTarget(configuration).version
    monkeypatch.setattr(target, "implementation_version", "future-test-implementation")
    assert target.version != version


@pytest.fixture(autouse=True)
def offline_target_environment(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    monkeypatch.setattr("src.targets._validate_resolved_destination", lambda *_: None)


class Response(BytesIO):
    def __init__(self, status=200, headers=None):
        super().__init__(b'{"answer":"Fictional answer"}')
        self.status = status
        self.headers = headers or {}
        self.read_calls = 0

    def read(self, *args):
        self.read_calls += 1
        if self.status >= 400:
            raise AssertionError("HTTP error bodies must not be read or exported")
        return super().read(*args)

    def geturl(self):
        return ENDPOINT


def target(opener, **configuration):
    return ExternalHTTPTarget(ExternalTargetConfig(name="Fixture", endpoint=ENDPOINT, **configuration), opener=opener)


def test_unconfigured_health_check_is_not_a_network_success():
    opener = Mock(side_effect=AssertionError("No health request is configured"))
    result = target(opener).health_check()
    assert result.status == ExecutionStatus.PENDING
    assert result.http_status is None
    assert result.metadata == {"health": "not_checked", "network_checked": False}
    assert result.error_code == "health_check_not_configured"
    assert "No network health check was performed" in result.safe_error
    opener.assert_not_called()


@pytest.mark.parametrize("raises", [False, True])
@pytest.mark.parametrize(
    "status,retryable",
    [
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (422, False),
        (408, True),
        (409, True),
        (429, True),
        (503, True),
    ],
)
def test_http_failures_preserve_safe_status_retryability_and_close_body(status, retryable, raises):
    body = Response(status)

    def opener(*args, **kwargs):
        if raises:
            raise HTTPError(ENDPOINT, status, "PRIVATE RESPONSE MESSAGE", {"Retry-After": "3"}, body)
        body.headers = {"Retry-After": "3"}
        return body

    result = target(opener).execute({"question": "Fixture"})
    assert result.http_status == status
    assert result.metadata["retryable"] is retryable
    assert result.metadata["retry_after_seconds"] == 3
    assert body.closed and body.read_calls == 0
    assert "PRIVATE RESPONSE MESSAGE" not in str(result)
    assert result.status == (ExecutionStatus.RATE_LIMITED if status == 429 else ExecutionStatus.FAILED)


@pytest.mark.parametrize("raises", [False, True])
def test_configured_health_check_retains_real_http_failure(raises):
    body = Response(401)

    def opener(*args, **kwargs):
        if raises:
            raise HTTPError(ENDPOINT, 401, "PRIVATE RESPONSE MESSAGE", {}, body)
        return body

    result = target(opener, health_check_path="health").health_check()
    assert result.status == ExecutionStatus.FAILED and result.http_status == 401
    assert result.metadata["network_checked"] is True
    assert result.metadata["retryable"] is False
    assert result.error_code == "external_authentication_error"
    assert body.closed and not body.read_calls


@pytest.mark.parametrize("retry_count", [0, 1, 3])
def test_target_retry_setting_is_used_when_engine_policy_is_not_overridden(retry_count):
    opener = Mock(side_effect=lambda *args, **kwargs: Response(503))
    engine = ExecutionEngine(target(opener, retry_count=retry_count), sleep=lambda _: None)
    record = engine.run([{"case_id": "fixture-case"}])[0]
    assert opener.call_count == record.attempt_count == retry_count + 1
    assert engine.policy.max_retries == retry_count


def test_explicit_run_retry_override_and_permanent_failure_are_honored():
    opener = Mock(side_effect=lambda *args, **kwargs: Response(503))
    record = ExecutionEngine(target(opener, retry_count=3), ExecutionPolicy(max_retries=0)).run(
        [{"case_id": "fixture"}]
    )[0]
    assert opener.call_count == record.attempt_count == 1
    denied = Mock(side_effect=lambda *args, **kwargs: Response(401))
    record = ExecutionEngine(target(denied, retry_count=3), sleep=lambda _: None).run([{"case_id": "fixture"}])[0]
    assert denied.call_count == record.attempt_count == 1


def test_retry_after_is_a_minimum_wait_and_excessive_wait_is_not_shortened():
    responses = [Response(429, {"Retry-After": "3"}), Response()]
    opener = Mock(side_effect=lambda *args, **kwargs: responses.pop(0))
    delays = []
    record = ExecutionEngine(target(opener, retry_count=1), sleep=delays.append).run([{"case_id": "fixture"}])[0]
    assert record.status == ExecutionStatus.PASSED and record.attempt_count == 2
    assert delays == [3]
    delayed = Mock(return_value=Response(429, {"Retry-After": "60"}))
    record = ExecutionEngine(target(delayed), sleep=delays.append).run([{"case_id": "fixture"}])[0]
    assert delayed.call_count == 1 and delays == [3]
    assert record.metadata["retry_suppressed"] == "retry_after_exceeds_wait_limit"


@pytest.mark.parametrize("hint", ["NaN", "Infinity", "-1", "PRIVATE HEADER VALUE", "x" * 129])
def test_invalid_retry_headers_are_not_exposed(hint):
    result = target(lambda *args, **kwargs: Response(503, {"Retry-After": hint})).execute({})
    assert "retry_after_seconds" not in result.metadata
    assert hint not in json.dumps(result.metadata)


def test_retry_after_http_date_and_oversized_hint():
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    result = target(lambda *args, **kwargs: Response(503, {"Retry-After": future})).execute({})
    assert 28 <= result.metadata["retry_after_seconds"] <= 30
    result = target(lambda *args, **kwargs: Response(503, {"Retry-After": "601"})).execute({})
    assert result.metadata["retryable"] is False
    assert result.metadata["retry_suppressed"] == "retry_after_exceeds_supported_limit"
    assert "retry_after_seconds" not in result.metadata


@pytest.mark.parametrize("retry_count", [-1, 11, True, False, 1.5, "2", None])
def test_invalid_target_retry_counts_are_rejected(retry_count):
    with pytest.raises(TargetConfigurationError, match="retry_count"):
        ExternalTargetConfig(name="Fixture", endpoint=ENDPOINT, retry_count=retry_count)
