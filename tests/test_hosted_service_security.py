from __future__ import annotations

import json
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pandas as pd
import pytest

from src import config, database, hosted_limits, llm_client, targets
from src.auth import AuthenticationError
from src.domain import ExecutionStatus
from src.evaluator import run_evaluation
from src.execution import ExecutionEngine, ExecutionPolicy
from src.public_sessions import end_public_session
from src.security import AuthorizationError
from src.targets import (
    ExternalHTTPTarget,
    ExternalTargetConfig,
    FoundationModelConfig,
    FoundationModelTarget,
    SecretResolver,
    SyntheticMockTarget,
    TargetConfigurationError,
)


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "hosted-session")
    monkeypatch.setattr(config, "APP_ENV", "hosted-beta")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    state = {}
    context = database.initialize_session(state)
    yield state, context, database.get_repository()
    end_public_session(state)


def provider_result(*args, **kwargs):
    return {"answer": "Keep records for 30 days.", "model": "observed-model", "latency_ms": 1, "metadata": {}}


def provider_target():
    return FoundationModelTarget(
        FoundationModelConfig("openai", "gpt-4o-mini", "secret://VISITOR"),
        SecretResolver({"VISITOR": "visitor-only-test-key"}),
    )


class Response(BytesIO):
    status = 200

    def geturl(self):
        return "https://assistant.example/answer"


def public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )


def test_online_workspaces_remain_isolated_and_memory_bounded(online):
    first, context, repository = online
    database.save_project({"name": "First private project"})
    second = {}
    try:
        other = database.initialize_session(second)
        assert database.get_repository().list_projects(other) == []
        with pytest.raises(AuthorizationError):
            repository.list_projects(other)
        database.initialize_session(first)
        assert repository.list_projects(context)[0]["name"] == "First private project"
        with repository.connection() as connection:
            pages = connection.execute("PRAGMA max_page_count").fetchone()[0]
            size = connection.execute("PRAGMA page_size").fetchone()[0]
        assert pages * size == hosted_limits.HOSTED_MAX_SESSION_DATABASE_BYTES
        budget = hosted_limits.current_session()
        end_public_session(first)
        assert budget is not None and budget.closed
        database.initialize_session(second)
        assert database.get_repository().list_projects(other) == []
    finally:
        end_public_session(second)


def test_hosted_mode_cannot_be_enabled_in_wasm(monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "hosted-session")
    monkeypatch.setattr(sys, "platform", "emscripten")
    assert not config.hosted_sessions_enabled()
    assert config.public_sessions_enabled()
    with pytest.raises(AuthenticationError, match="native server"):
        database.initialize_session({})


def test_visitor_provider_call_never_uses_owner_keys(online, monkeypatch):
    monkeypatch.setenv("VISITOR", "owner-environment-key")
    monkeypatch.setattr(config, "PROVIDER_API_KEYS", {"openai": "owner-provider-key"})
    observed = []

    def answer(*args, **kwargs):
        observed.append(args[2])
        return provider_result()

    monkeypatch.setattr(llm_client, "_openai_answer", answer)
    missing = llm_client.generate_answer("question", "source", "instruction", "gpt-4o-mini")
    assert missing["error_code"] == "missing_api_key"
    assert not observed
    with pytest.raises(TargetConfigurationError, match="not configured"):
        SecretResolver(environment_names=["VISITOR"]).resolve("secret://VISITOR")
    result = provider_target().execute({"question": "question"})
    assert result.status == ExecutionStatus.PASSED
    assert observed == ["visitor-only-test-key"]
    assert config.api_key_for_provider("openai") == ""


def test_threaded_provider_calls_keep_captured_session_budget(online, monkeypatch):
    monkeypatch.setattr(llm_client, "_openai_answer", provider_result)
    budget = hosted_limits.current_session()
    results = ExecutionEngine(provider_target(), ExecutionPolicy(max_concurrency=2, max_retries=0)).run(
        [{"case_id": "first", "question": "one"}, {"case_id": "second", "question": "two"}]
    )
    assert all(result.status == ExecutionStatus.PASSED for result in results)
    assert budget is not None and len(budget.calls) == 2 and budget.active_calls == 0
    with ThreadPoolExecutor(max_workers=1) as executor:
        unbound = executor.submit(
            llm_client.generate_answer, "question", "context", "prompt", "gpt-4o-mini", "visitor-only-test-key"
        ).result()
    assert unbound["error_code"] == "hosted_capacity_limit"
    assert len(budget.calls) == 2


def test_provider_preflight_and_retries_share_session_call_budget(online, monkeypatch):
    monkeypatch.setattr(hosted_limits, "HOSTED_SESSION_CALLS_PER_WINDOW", 1)
    monkeypatch.setattr(llm_client, "_openai_answer", provider_result)
    first = llm_client.generate_answer("question", "context", "prompt", "gpt-4o-mini", "visitor-only-test-key")
    second = provider_target().execute({"question": "question"})
    assert first["status"] == "passed"
    assert second.status == ExecutionStatus.RATE_LIMITED
    assert second.metadata["quality_score_eligible"] is False
    assert second.metadata["retryable"] is False


def test_closed_session_target_cannot_continue_outbound_calls(online, monkeypatch):
    monkeypatch.setattr(llm_client, "_openai_answer", lambda *_args, **_kwargs: pytest.fail("Unexpected provider call"))
    target = provider_target()
    end_public_session(online[0])
    assert target.execute({"question": "question"}).error_code == "hosted_capacity_limit"


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://assistant.example/answer",
        "https://127.0.0.1/answer",
        "https://[::1]/answer",
        "https://169.254.169.254/metadata",
        "https://[::ffff:127.0.0.1]/answer",
        "https://assistant.example:8443/answer",
    ],
)
def test_hosted_endpoints_cannot_reach_private_networks_or_other_ports(online, monkeypatch, endpoint):
    monkeypatch.setattr(config, "ALLOW_PRIVATE_EXTERNAL_TARGETS", True)
    with pytest.raises(TargetConfigurationError):
        ExternalTargetConfig("Assistant", endpoint)


def test_visitor_https_target_and_health_share_admission_without_operator_allowlist(online, monkeypatch):
    public_dns(monkeypatch)
    monkeypatch.setattr(hosted_limits, "HOSTED_SESSION_CALLS_PER_WINDOW", 1)
    seen = []

    def opener(request, **kwargs):
        seen.append(request)
        return Response(b'{"answer":"Keep records for 30 days."}')

    target = ExternalHTTPTarget(
        ExternalTargetConfig("Assistant", "https://assistant.example/answer", health_check_path="/health"),
        opener=opener,
    )
    assert target.execute({"question": "question"}).status == ExecutionStatus.PASSED
    assert target.health_check().error_code == "hosted_capacity_limit"
    assert len(seen) == 1


def test_private_dns_answer_fails_before_http_even_with_private_flag(online, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_PRIVATE_EXTERNAL_TARGETS", True)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))],
    )
    target = ExternalHTTPTarget(
        ExternalTargetConfig("Assistant", "https://assistant.example/answer"),
        opener=lambda *_args, **_kwargs: pytest.fail("Private destination reached opener"),
    )
    assert target.execute({"question": "question"}).error_code == "external_destination_blocked"


@pytest.mark.parametrize("options", [{"method": "PATCH"}, {"timeout_seconds": 31}, {"retry_count": 2}])
def test_hosted_target_configuration_enforces_shared_server_bounds(online, options):
    with pytest.raises(TargetConfigurationError):
        ExternalTargetConfig("Assistant", "https://assistant.example/answer", **options)


def test_process_capacity_and_rate_do_not_reset_with_a_new_visitor(online, monkeypatch):
    first = hosted_limits.current_session()
    other = hosted_limits.new_session_budget()
    try:
        monkeypatch.setattr(hosted_limits, "HOSTED_MAX_PROCESS_CALLS", 1)
        with hosted_limits.call_scope(first), pytest.raises(hosted_limits.HostedLimitError, match="busy"):
            with hosted_limits.call_scope(other):
                pytest.fail("Process concurrency limit bypassed")
        assert other.active_calls == 0
        monkeypatch.setattr(hosted_limits, "HOSTED_PROCESS_CALLS_PER_WINDOW", 0)
        with pytest.raises(hosted_limits.HostedLimitError, match="short-term"):
            with hosted_limits.call_scope(other):
                pytest.fail("Process rate limit bypassed")
    finally:
        other.close()


def test_duplicate_run_and_session_capacity_fail_closed_and_release(online, monkeypatch):
    with hosted_limits.run_scope(), pytest.raises(hosted_limits.HostedLimitError, match="already running"):
        with hosted_limits.run_scope():
            pytest.fail("Duplicate run admitted")
    with hosted_limits.run_scope():
        assert hosted_limits.current_session().active_run
    monkeypatch.setattr(hosted_limits, "HOSTED_MAX_ACTIVE_SESSIONS", 0)
    with pytest.raises(hosted_limits.HostedLimitError, match="capacity"):
        hosted_limits.new_session_budget()


def test_oversized_evaluation_fails_before_persistence_or_retrieval(online, monkeypatch):
    case = {
        "question": "Question",
        "expected_answer": "Answer",
        "expected_source": "Policy",
        "category": "Policy",
        "should_escalate": False,
    }
    frame = pd.DataFrame([{**case, "case_id": f"case-{index}"} for index in range(101)])
    monkeypatch.setattr(
        online[2], "create_dataset_version", lambda *_args, **_kwargs: pytest.fail("Oversized run persisted")
    )
    with pytest.raises(hosted_limits.HostedLimitError, match="100"):
        run_evaluation(
            frame, [], {"Current": "Use sources"}, "mock-model", 3, 0.05, 3500, 0.03, "test", max_concurrency=2
        )
    assert not hosted_limits.current_session().active_run


@pytest.mark.parametrize(
    "policy", [ExecutionPolicy(max_concurrency=3, max_retries=0), ExecutionPolicy(max_concurrency=1, max_retries=2)]
)
def test_direct_engine_cannot_exceed_hosted_bounds(online, policy):
    with pytest.raises(hosted_limits.HostedLimitError):
        ExecutionEngine(SyntheticMockTarget(), policy).run([{"case_id": "one"}])


def test_config_caps_cannot_be_loosened_and_worker_never_loads_dotenv():
    script = """
import sys, types, json
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda *a, **k: (_ for _ in ()).throw(AssertionError('dotenv loaded')))
from src import config
print(json.dumps([config.MAX_UPLOAD_BYTES, config.MAX_DOCUMENTS_PER_UPLOAD, config.MAX_DATASET_ROWS, config.MAX_EXTRACTED_CHARACTERS]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={
            "APP_ACCESS_MODE": "hosted-session",
            "STUDIO_EXTRACTION_WORKER": "1",
            "MAX_UPLOAD_BYTES": "99999999",
            "MAX_DOCUMENTS_PER_UPLOAD": "999",
            "MAX_DATASET_ROWS": "9999",
            "MAX_EXTRACTED_CHARACTERS": "99999999",
        },
    )
    assert json.loads(result.stdout) == [2 * 1024 * 1024, 8, 500, 250_000]


def test_trickling_response_has_one_total_deadline_and_releases_admission(online, monkeypatch):
    public_dns(monkeypatch)
    clock = [100.0]
    monkeypatch.setattr(targets.time, "monotonic", lambda: clock[0])

    class SlowResponse(Response):
        def read1(self, size):
            clock[0] += 0.6
            return super().read1(1)

    response = SlowResponse(b'{"answer":"slow"}')
    target = ExternalHTTPTarget(
        ExternalTargetConfig("Assistant", "https://assistant.example/answer", timeout_seconds=1),
        opener=lambda *_args, **_kwargs: response,
    )
    result = target.execute({"question": "question"})
    assert result.status == ExecutionStatus.TIMED_OUT
    assert result.answer == ""
    assert response.closed
    assert hosted_limits.current_session().active_calls == 0


def test_hosted_response_reader_stops_at_byte_cap(online):
    response = Response(b"x" * 200_000)
    assert len(targets._read_external_response(response, 100_000, 1)) == 100_001
    assert response.tell() == 100_001


def test_http_response_content_length_completion_does_not_touch_closed_socket(online):
    # Match urllib's Connection: close lifecycle, using only an AF_UNIX pair.
    # The socket file owns the descriptor until read1 consumes the last byte.
    client, server = socket.socketpair()
    try:
        body = b'{"answer":"complete"}'
        server.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        response = targets._DeadlineHTTPResponse(client)
        response.begin()
        response._studio_socket = client
        client.close()
        assert targets._read_external_response(response, 200_000, 1) == body
        assert response.isclosed()
        assert client.fileno() == -1
    finally:
        client.close()
        server.close()


def test_connection_watchdog_interrupts_socket_and_response_close_cancels_timer(online, monkeypatch):
    shutdowns, deadlines, timeouts = [], [], []

    class FakeSocket:
        def settimeout(self, timeout):
            timeouts.append(timeout)

        def connect(self, address):
            assert address == ("93.184.216.34", 443)

        def shutdown(self, how):
            shutdowns.append(how)

        def close(self):
            pass

    class FakeTimer:
        cancelled = False

        def __init__(self, delay, callback):
            deadlines.append(delay)
            self.callback = callback

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    connection = targets._PinnedHTTPSConnection(
        "assistant.example",
        timeout=0.1,
        addresses=(targets._ResolvedAddress(socket.AF_INET, socket.SOCK_STREAM, 6, ("93.184.216.34", 443)),),
    )
    monkeypatch.setattr(targets.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(targets.threading, "Timer", FakeTimer)
    monkeypatch.setattr(connection._context, "wrap_socket", lambda sock, **_kwargs: sock)
    connection.connect()
    assert 0 < deadlines[0] <= 0.1
    assert all(0 < timeout <= 0.1 for timeout in timeouts)
    connection._deadline_timer.callback()
    assert shutdowns == [socket.SHUT_RDWR]
    # Exercise the real HTTPResponse lifecycle without any network operation.
    response = targets._DeadlineHTTPResponse.__new__(targets._DeadlineHTTPResponse)
    response.fp = None
    response._studio_timer = connection._deadline_timer
    response.close()
    assert connection._deadline_timer.cancelled
