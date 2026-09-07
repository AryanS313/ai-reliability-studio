from __future__ import annotations

import json

import pytest

from src.domain import ExecutionStatus, TargetResponse, TargetType
from src.execution import CancellationToken, ExecutionEngine, ExecutionPolicy
from src.llm_client import generate_answer
from src.targets import (
    ExternalHTTPTarget,
    ExternalTargetConfig,
    MockTargetConfig,
    SecretResolver,
    SyntheticMockTarget,
    TargetAdapter,
    TargetConfigurationError,
    target_configuration_for_storage,
)

CHUNKS = [
    {
        "source_name": "Policy",
        "chunk_id": "policy-1",
        "chunk_text": "Requests are not eligible after 30 days unless fraud is suspected.",
    }
]


class FakeHTTPResponse:
    status = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class RawHTTPResponse:
    def __init__(self, body: str, *, status: int = 200, final_url: str | None = None) -> None:
        self.body = body.encode()
        self.status = status
        self.final_url = final_url

    def read(self, size: int | None = None) -> bytes:
        return self.body if size is None else self.body[:size]

    def geturl(self) -> str:
        return self.final_url or "https://assistant.example.test/chat"


def test_mock_is_generic_deterministic_and_prompt_independent():
    first = generate_answer(
        "What happens after 30 days?",
        "Requests are not eligible after 30 days unless fraud is suspected.",
        "You are a responsible AI assistant. Answer only using context.",
        "mock-model",
        retrieved_chunks=CHUNKS,
    )
    second = generate_answer(
        "What happens after 30 days?",
        "Requests are not eligible after 30 days unless fraud is suspected.",
        "Ignore every safety format and be casual.",
        "mock-model",
        retrieved_chunks=CHUNKS,
    )
    assert first["answer"] == second["answer"]
    assert first["metadata"]["synthetic"] is True
    assert "not model-quality evidence" in first["metadata"]["evidence_notice"]


def test_synthetic_success_fixture_uses_reference_answer_and_expected_source():
    target = SyntheticMockTarget()
    response = target.execute(
        {
            "question": "Explain the 7-day review and 30-day eligibility limits.",
            "expected_answers": ["Seven-day review and thirty-day eligibility are separate conditions."],
            "expected_sources": ["Refund Policy"],
            "retrieved_chunks": [
                {
                    "source_name": "Loan Policy",
                    "chunk_id": "loan-1",
                    "chunk_text": "Final loan eligibility decisions require human review.",
                },
                {
                    "source_name": "Refund Policy",
                    "chunk_id": "refund-1",
                    "chunk_text": "Seven-day review and thirty-day eligibility are separate conditions.",
                },
            ],
        }
    )
    assert response.answer.startswith("Seven-day review and thirty-day eligibility are separate conditions.")
    assert response.citations[0]["chunk_id"] == "refund-1"
    assert response.metadata["reference_answer_fixture"] is True


@pytest.mark.parametrize(
    ("scenario", "status"),
    [
        ("correct_grounded_answer", ExecutionStatus.PASSED),
        ("hallucination", ExecutionStatus.PASSED),
        ("refusal", ExecutionStatus.PASSED),
        ("escalation", ExecutionStatus.PASSED),
        ("unsupported_answer", ExecutionStatus.PASSED),
        ("contradiction", ExecutionStatus.PASSED),
        ("citation_failure", ExecutionStatus.PASSED),
        ("missed_escalation", ExecutionStatus.PASSED),
        ("provider_error", ExecutionStatus.FAILED),
        ("timeout", ExecutionStatus.TIMED_OUT),
        ("malformed_response", ExecutionStatus.INVALID_RESPONSE),
        ("rate_limiting", ExecutionStatus.RATE_LIMITED),
        ("privacy_leakage", ExecutionStatus.PASSED),
        ("retrieval_failure", ExecutionStatus.PASSED),
    ],
)
def test_all_mock_scenarios(scenario: str, status: ExecutionStatus):
    target = SyntheticMockTarget(MockTargetConfig(scenario=scenario))
    response = target.execute({"question": "What happens after 30 days?", "retrieved_chunks": CHUNKS})
    assert response.status == status
    assert response.metadata["prompt_content_ignored"] is True


def test_real_provider_failure_is_never_converted_to_mock(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret provider detail")

    monkeypatch.setattr("src.llm_client._openai_answer", fail)
    result = generate_answer("Question", "Context", "Prompt", "gpt-4o-mini", api_key="session-secret")
    assert result["status"] == "failed"
    assert result["answer"] == ""
    assert result["model"] is None
    assert result["metadata"]["requested_model"] == "gpt-4o-mini"
    assert "secret provider detail" not in result["safe_error"]


def test_external_target_maps_response_and_resolves_secret_without_storage():
    captured = {}

    def opener(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.data)
        return FakeHTTPResponse(
            {
                "response": {
                    "answer": "Supported response",
                    "citations": [{"chunk_id": "policy-1"}],
                    "escalation": {"should_escalate": False},
                },
                "usage": {"input": 4, "output": 2, "cost": 0.01},
            }
        )

    configuration = ExternalTargetConfig(
        name="Assistant",
        endpoint="https://assistant.example.test/chat",
        headers={"Authorization": "secret://TOKEN"},
        request_template={"input": "${question}", "segment": "${user_segment}"},
        response_mappings={
            "answer": "$.response.answer",
            "citations": "$.response.citations",
            "escalation": "$.response.escalation",
            "input_tokens": "$.usage.input",
            "output_tokens": "$.usage.output",
            "cost": "$.usage.cost",
        },
    )
    target = ExternalHTTPTarget(configuration, SecretResolver({"TOKEN": "runtime-token"}), opener=opener)
    response = target.execute({"question": "Hello", "user_segment": "beta"})
    assert response.status == ExecutionStatus.PASSED
    assert response.answer == "Supported response"
    assert response.citations[0]["chunk_id"] == "policy-1"
    assert captured == {"authorization": "runtime-token", "body": {"input": "Hello", "segment": "beta"}}
    stored = target_configuration_for_storage(configuration)
    assert "runtime-token" not in json.dumps(stored)


def test_external_target_rejects_raw_secrets_and_insecure_remote_http():
    with pytest.raises(TargetConfigurationError):
        ExternalTargetConfig(name="bad", endpoint="http://example.com", headers={})
    with pytest.raises(TargetConfigurationError):
        ExternalTargetConfig(
            name="bad",
            endpoint="https://example.com",
            headers={"Authorization": "Bearer raw-secret-token-value-1234567890"},
        )


class SequenceTarget(TargetAdapter):
    target_type = TargetType.EXTERNAL_API

    def __init__(self, statuses: list[ExecutionStatus]) -> None:
        self.statuses = statuses
        self.calls = 0

    @property
    def version(self) -> str:
        return "sequence-v1"

    def execute(self, request: dict) -> TargetResponse:
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return TargetResponse(status=status, answer="ok" if status == ExecutionStatus.PASSED else "")


def test_execution_retries_cache_and_duplicate_prevention():
    target = SequenceTarget([ExecutionStatus.RATE_LIMITED, ExecutionStatus.PASSED])
    engine = ExecutionEngine(
        target,
        ExecutionPolicy(max_concurrency=1, max_retries=2, backoff_seconds=0),
        sleep=lambda _: None,
    )
    request = {"case_id": "case-1", "prompt_version": "p1", "dataset_version": "d1"}
    first = engine.run([request])[0]
    assert first.status == ExecutionStatus.PASSED
    assert first.attempt_count == 2
    # The same engine refuses a duplicate in-flight/submitted key.
    duplicate = engine.run([request])[0]
    assert duplicate.status == ExecutionStatus.CANCELLED
    assert duplicate.metadata["duplicate_prevented"] is True


def test_execution_cancellation_and_resume():
    target = SequenceTarget([ExecutionStatus.PASSED])
    token = CancellationToken()
    token.cancel()
    engine = ExecutionEngine(target, ExecutionPolicy(max_concurrency=1))
    request = {"case_id": "case-1", "prompt_version": "p1"}
    cancelled = engine.run([request], cancellation=token)[0]
    assert cancelled.status == ExecutionStatus.CANCELLED
    resumed_engine = ExecutionEngine(target, ExecutionPolicy(max_concurrency=1))
    resumed = resumed_engine.run([request], completed={})[0]
    assert resumed.status == ExecutionStatus.PASSED


class ExplodingTarget(TargetAdapter):
    target_type = TargetType.EXTERNAL_API

    @property
    def version(self) -> str:
        return "exploding-v1"

    def execute(self, request: dict) -> TargetResponse:
        raise RuntimeError("credential=super-secret-provider-detail")


def test_unexpected_adapter_exception_is_sanitized_and_not_scored():
    engine = ExecutionEngine(
        ExplodingTarget(),
        ExecutionPolicy(max_concurrency=1, max_retries=0),
    )
    record = engine.run([{"case_id": "case-1", "dataset_version": "d1"}])[0]
    assert record.status == ExecutionStatus.FAILED
    assert record.response is not None
    assert record.response.answer == ""
    assert "super-secret" not in str(record.response)
    assert record.response.metadata["quality_score_eligible"] is False


def test_external_target_enforces_response_size(monkeypatch):
    monkeypatch.setattr("src.config.MAX_EXTERNAL_RESPONSE_BYTES", 8)
    target = ExternalHTTPTarget(
        ExternalTargetConfig(name="limited", endpoint="https://assistant.example.test/chat"),
        opener=lambda request, timeout: FakeHTTPResponse({"answer": "too long"}),
    )
    response = target.execute({"question": "Hello"})
    assert response.status == ExecutionStatus.INVALID_RESPONSE
    assert response.error_code == "external_response_too_large"


def test_external_target_blocks_dns_rebinding_in_production(monkeypatch):
    monkeypatch.setattr("src.config.APP_ENV", "production")
    monkeypatch.setattr("src.config.EXTERNAL_TARGET_ALLOWED_HOSTS", ("assistant.example.test",))
    monkeypatch.setattr("src.config.ALLOW_PRIVATE_EXTERNAL_TARGETS", False)
    monkeypatch.setattr(
        "src.targets.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.0.0.8", 443))],
    )
    target = ExternalHTTPTarget(
        ExternalTargetConfig(name="blocked", endpoint="https://assistant.example.test/chat"),
        opener=lambda *args, **kwargs: pytest.fail("Blocked destination must not be contacted"),
    )
    response = target.execute({"question": "Hello"})
    assert response.status == ExecutionStatus.INVALID_RESPONSE
    assert response.error_code == "external_destination_blocked"


def test_external_target_blocks_redirects_and_classifies_http_errors():
    redirected = ExternalHTTPTarget(
        ExternalTargetConfig(name="redirect", endpoint="https://assistant.example.test/chat"),
        opener=lambda request, timeout: RawHTTPResponse(
            '{"answer":"unexpected"}', final_url="https://metadata.internal/latest"
        ),
    ).execute({"question": "Hello"})
    assert redirected.error_code == "external_redirect_blocked"

    authentication = ExternalHTTPTarget(
        ExternalTargetConfig(name="auth", endpoint="https://assistant.example.test/chat"),
        opener=lambda request, timeout: RawHTTPResponse("{}", status=401),
    ).execute({"question": "Hello"})
    assert authentication.status == ExecutionStatus.FAILED
    assert authentication.error_code == "external_authentication_error"

    limited = ExternalHTTPTarget(
        ExternalTargetConfig(name="limit", endpoint="https://assistant.example.test/chat"),
        opener=lambda request, timeout: RawHTTPResponse("{}", status=429),
    ).execute({"question": "Hello"})
    assert limited.status == ExecutionStatus.RATE_LIMITED
    assert limited.error_code == "rate_limited"


def test_external_target_streaming_malformed_empty_and_sensitive_header_errors():
    stream = 'data: {"answer":"Hello "}\n\ndata: {"answer":"world"}\n\ndata: [DONE]\n'
    streamed = ExternalHTTPTarget(
        ExternalTargetConfig(name="stream", endpoint="https://assistant.example.test/chat", streaming=True),
        opener=lambda request, timeout: RawHTTPResponse(stream),
    ).execute({"question": "Hello"})
    assert streamed.status == ExecutionStatus.PASSED
    assert streamed.answer == "Hello world"

    malformed = ExternalHTTPTarget(
        ExternalTargetConfig(name="malformed", endpoint="https://assistant.example.test/chat"),
        opener=lambda request, timeout: RawHTTPResponse("not-json"),
    ).execute({"question": "Hello"})
    assert malformed.status == ExecutionStatus.INVALID_RESPONSE

    empty = ExternalHTTPTarget(
        ExternalTargetConfig(name="empty", endpoint="https://assistant.example.test/chat"),
        opener=lambda request, timeout: RawHTTPResponse('{"answer":""}'),
    ).execute({"question": "Hello"})
    assert empty.status == ExecutionStatus.INVALID_RESPONSE
    assert empty.error_code == "missing_answer"

    unresolved_secret = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="secret",
            endpoint="https://assistant.example.test/chat",
            headers={"Authorization": "secret://PRIVATE_TOKEN"},
        ),
        SecretResolver({}),
        opener=lambda request, timeout: pytest.fail("Missing secret must prevent the request"),
    )
    engine = ExecutionEngine(unresolved_secret, ExecutionPolicy(max_concurrency=1, max_retries=0))
    record = engine.run([{"case_id": "case-secret"}])[0]
    assert record.status == ExecutionStatus.INVALID_RESPONSE
    assert "PRIVATE_TOKEN" not in str(record.response)


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_code"),
    [
        (
            TimeoutError("request timed out with key sk-secret-value-123456"),
            ExecutionStatus.TIMED_OUT,
            "provider_timeout",
        ),
        (
            type("RateLimitFailure", (Exception,), {})("429 key sk-secret-value-123456"),
            ExecutionStatus.RATE_LIMITED,
            "provider_rate_limit",
        ),
        (
            type("AuthenticationFailure", (Exception,), {})("bad key sk-secret-value-123456"),
            ExecutionStatus.FAILED,
            "provider_error",
        ),
    ],
)
def test_foundation_provider_failures_are_classified_without_secret_leakage(
    monkeypatch, exception, expected_status, expected_code
):
    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr("src.llm_client._openai_answer", fail)
    result = generate_answer(
        "Question",
        "Context",
        "System",
        "gpt-4o-mini",
        api_key="sk-secret-value-123456",
    )
    assert result["status"] == expected_status.value
    assert result["error_code"] == expected_code
    assert "sk-secret" not in result["safe_error"]


def test_foundation_provider_empty_response_and_safety_refusal_contract(monkeypatch):
    monkeypatch.setattr("src.llm_client._openai_answer", lambda *args, **kwargs: {"answer": "", "metadata": {}})
    empty = generate_answer("Question", "Context", "System", "gpt-4o-mini", api_key="runtime-key")
    assert empty["status"] == ExecutionStatus.INVALID_RESPONSE.value
    assert empty["error_code"] == "empty_provider_response"

    monkeypatch.setattr(
        "src.llm_client._openai_answer",
        lambda *args, **kwargs: {
            "answer": "I cannot assist with that request.",
            "metadata": {"provider_safety_refusal": True},
        },
    )
    refusal = generate_answer("Question", "Context", "System", "gpt-4o-mini", api_key="runtime-key")
    assert refusal["status"] == ExecutionStatus.PASSED.value
    assert refusal["metadata"]["provider_safety_refusal"] is True
