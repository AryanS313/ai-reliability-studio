"""Exercise the pinned provider SDKs over HTTPX MockTransport, never provider APIs."""

from __future__ import annotations

import json
import socket

import httpx
import pandas as pd
import pytest

from src import config, database, llm_client
from src.domain import ExecutionStatus
from src.evaluator import run_evaluation
from src.storage import SQLiteRepository
from src.targets import FoundationModelConfig, FoundationModelTarget, SecretResolver


@pytest.fixture(autouse=True)
def forbid_network_and_select_public_mode(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("These tests must not open network connections.")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(config, "AUTH_MODE", "public-session")


def mock_transport(monkeypatch, handler):
    requests = []
    clients = []
    original = llm_client._http_client

    def handle(request):
        requests.append(request)
        return handler(request)

    def create():
        client = original(transport=httpx.MockTransport(handle))
        clients.append(client)
        return client

    monkeypatch.setattr(llm_client, "_http_client", create)
    return requests, clients


def openai_payload(*, model="observed-openai-version", refusal=None):
    payload = {
        "id": "chatcmpl-offline",
        "object": "chat.completion",
        "created": 1,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None if refusal else "Offline answer.",
                    "refusal": refusal,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
    if model is not None:
        payload["model"] = model
    return payload


def anthropic_payload(*, model="observed-claude-version", refusal=False):
    payload = {
        "id": "msg-offline",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "I cannot help." if refusal else "Offline answer."}],
        "stop_reason": "refusal" if refusal else "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }
    if model is not None:
        payload["model"] = model
    return payload


def gemini_payload(*, model="observed-gemini-version", refusal=False):
    payload = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": "Offline answer."}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3, "totalTokenCount": 8},
    }
    if refusal:
        payload["candidates"] = []
        payload["promptFeedback"] = {
            "blockReason": "SAFETY",
            "blockReasonMessage": "Offline provider safety explanation.",
            "safetyRatings": [{"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "HIGH", "blocked": True}],
        }
    if model is not None:
        payload["modelVersion"] = model
    return payload


PROVIDERS = [
    ("gpt-4o-mini", "api.openai.com", "/v1/chat/completions", openai_payload),
    ("claude-3-5-haiku-20241022", "api.anthropic.com", "/v1/messages", anthropic_payload),
    ("claude-sonnet-5", "api.anthropic.com", "/v1/messages", anthropic_payload),
    ("claude-haiku-4-5", "api.anthropic.com", "/v1/messages", anthropic_payload),
    (
        "gemini-2.0-flash",
        "generativelanguage.googleapis.com",
        "/v1beta/models/gemini-2.0-flash:generateContent",
        gemini_payload,
    ),
]


@pytest.mark.parametrize("model,host,path,payload_factory", PROVIDERS)
def test_real_sdk_serialization_identity_usage_and_resource_cleanup(monkeypatch, model, host, path, payload_factory):
    requests, clients = mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload_factory()))
    result = llm_client.generate_answer("Question", "Context", "System", model, api_key="visitor-fixture-key", seed=12)
    assert result["status"] == ExecutionStatus.PASSED.value
    assert result["model"] == payload_factory().get("model", payload_factory().get("modelVersion"))
    assert result["metadata"]["requested_model"] == model
    assert result["metadata"]["model_identity_provenance"] == "provider_response"
    assert result["metadata"]["token_usage_source"] == "provider"
    assert (result["input_tokens"], result["output_tokens"]) == (5, 3)
    assert len(requests) == 1
    request = requests[0]
    assert request.url.host == host
    assert request.url.path == path
    body = json.loads(request.content)
    if model.startswith("gemini"):
        assert body["generationConfig"]["seed"] == 12
        assert "Question" in body["contents"][0]["parts"][0]["text"]
    else:
        assert body["model"] == model
        assert "Question" in body["messages"][0]["content"]
    assert all(0 < seconds <= 30 for seconds in request.extensions["timeout"].values())
    assert all(client.is_closed and not client.trust_env and not client.follow_redirects for client in clients)


@pytest.mark.parametrize("model,host,path,payload_factory", PROVIDERS)
def test_public_client_does_not_inherit_owner_sdk_environment(monkeypatch, model, host, path, payload_factory):
    fake_environment = {
        "OPENAI_API_KEY": "owner-openai-key",
        "OPENAI_ORG_ID": "owner-org",
        "OPENAI_PROJECT_ID": "owner-project",
        "OPENAI_BASE_URL": "https://owner-proxy.invalid/v1",
        "ANTHROPIC_API_KEY": "owner-anthropic-key",
        "ANTHROPIC_AUTH_TOKEN": "owner-auth-token",
        "ANTHROPIC_BASE_URL": "https://owner-proxy.invalid",
        "HTTP_PROXY": "http://owner-proxy.invalid",
        "HTTPS_PROXY": "http://owner-proxy.invalid",
        "ALL_PROXY": "http://owner-proxy.invalid",
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GOOGLE_API_KEY": "owner-google-key",
        "GOOGLE_CLOUD_PROJECT": "owner-project",
        "GOOGLE_CLOUD_LOCATION": "owner-location",
        "GOOGLE_GENAI_CLIENT_MODE": "record",
        "GOOGLE_GENAI_REPLAYS_DIRECTORY": "/must-not-be-opened",
        "GOOGLE_GENAI_REPLAY_ID": "owner-replay",
        "NETRC": "/must-not-be-opened",
    }
    for name, value in fake_environment.items():
        monkeypatch.setenv(name, value)
    requests, clients = mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload_factory()))
    result = llm_client.generate_answer("Question", "Context", "System", model, api_key="visitor-fixture-key")
    assert result["status"] == ExecutionStatus.PASSED.value
    assert len(requests) == 1
    request = requests[0]
    assert request.url.host == host
    assert request.url.path == path
    header_values = " ".join(request.headers.values())
    assert "owner-" not in str(request.url) + header_values + request.content.decode()
    assert "visitor-fixture-key" in header_values
    assert "openai-organization" not in request.headers
    assert "openai-project" not in request.headers
    assert all(not client.trust_env and client.is_closed for client in clients)


@pytest.mark.parametrize("model,host,path,payload_factory", PROVIDERS)
def test_unreported_model_stays_unknown(monkeypatch, model, host, path, payload_factory):
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload_factory(model=None)))
    result = llm_client.generate_answer("Question", "Context", "System", model, api_key="visitor-fixture-key")
    assert result["status"] == ExecutionStatus.PASSED.value
    assert result["model"] is None
    assert result["metadata"]["requested_model"] == model
    assert result["metadata"]["model_identity_provenance"] == "not_reported"


@pytest.mark.parametrize("model,host,path,payload_factory", PROVIDERS)
def test_provider_safety_refusal_survives_actual_sdk_parsing(monkeypatch, model, host, path, payload_factory):
    refusal = "I cannot help." if model.startswith("gpt") else True
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload_factory(refusal=refusal)))
    result = llm_client.generate_answer("Question", "Context", "System", model, api_key="visitor-fixture-key")
    assert result["status"] == ExecutionStatus.PASSED.value
    assert result["metadata"]["provider_safety_refusal"] is True
    if not model.startswith("gemini"):
        assert result["answer"] == "I cannot help."
        assert result["metadata"]["provider_refusal_text"] == "I cannot help."
    else:
        assert result["answer"] == ""
        assert result["metadata"]["provider_block_reason"] == "SAFETY"
        assert result["metadata"]["provider_block_reason_message"] == "Offline provider safety explanation."
        assert result["metadata"]["provider_prompt_safety_ratings"][0]["blocked"] is True


@pytest.mark.parametrize("model,host,path,payload_factory", PROVIDERS)
@pytest.mark.parametrize("status", [429, 500, 307])
def test_sdk_does_not_retry_or_follow_redirect_and_closes_on_error(
    monkeypatch, model, host, path, payload_factory, status
):
    requests, clients = mock_transport(
        monkeypatch,
        lambda request: httpx.Response(
            status,
            json={"error": {"message": "offline failure", "type": "api_error"}},
            headers={"location": "https://other.invalid/", "retry-after": "0"},
        ),
    )
    result = llm_client.generate_answer("Question", "Context", "System", model, api_key="visitor-fixture-key")
    assert result["status"] == (ExecutionStatus.RATE_LIMITED.value if status == 429 else ExecutionStatus.FAILED.value)
    assert len(requests) == 1
    assert result["model"] is None
    assert result["metadata"]["requested_model"] == model
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("model,host,path,payload_factory", PROVIDERS)
def test_transport_timeouts_close_resources_without_retry(monkeypatch, model, host, path, payload_factory):
    def timeout(request):
        raise httpx.ReadTimeout("offline timeout", request=request)

    requests, clients = mock_transport(monkeypatch, timeout)
    result = llm_client.generate_answer("Question", "Context", "System", model, api_key="visitor-fixture-key")
    assert result["status"] == ExecutionStatus.TIMED_OUT.value
    assert len(requests) == 1
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("observed_model", ["actual-version", None])
def test_foundation_adapter_preserves_observed_identity_and_request_metadata(monkeypatch, observed_model):
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=openai_payload(model=observed_model)))
    target = FoundationModelTarget(
        FoundationModelConfig(provider="openai", model="gpt-4o-mini", api_key_reference="secret://openai"),
        SecretResolver({"openai": "visitor-fixture-key"}),
    )
    result = target.execute({"question": "Question", "context": "Context", "system_prompt": "System"})
    assert result.status == ExecutionStatus.PASSED
    assert result.model == observed_model
    assert result.provider == "openai"
    assert result.metadata["requested_model"] == "gpt-4o-mini"


def test_private_openai_keeps_explicit_environment_routing(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://private-approved.invalid/v1")
    monkeypatch.setenv("OPENAI_ORG_ID", "private-org")
    requests, clients = mock_transport(monkeypatch, lambda request: httpx.Response(200, json=openai_payload()))
    result = llm_client.generate_answer("Question", "Context", "System", "gpt-4o-mini", api_key="private-fixture-key")
    assert result["status"] == ExecutionStatus.PASSED.value
    assert requests[0].url.host == "private-approved.invalid"
    assert requests[0].headers["openai-organization"] == "private-org"
    assert clients[0].trust_env


def test_invalid_empty_provider_response_still_preserves_reported_model(monkeypatch):
    payload = openai_payload()
    payload["choices"][0]["message"]["content"] = ""
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
    result = llm_client.generate_answer("Question", "Context", "System", "gpt-4o-mini", api_key="visitor-fixture-key")
    assert result["status"] == ExecutionStatus.INVALID_RESPONSE.value
    assert result["model"] == "observed-openai-version"
    assert result["metadata"]["quality_score_eligible"] is False
    assert result["metadata"]["requested_model"] == "gpt-4o-mini"


@pytest.mark.parametrize("temperature", [0.0, 0.7, 1.0])
def test_configured_sonnet_five_omits_sampling_and_reads_text_after_thinking(monkeypatch, temperature):
    assert config.ANTHROPIC_MODEL_A == "claude-sonnet-5"

    def provider(request):
        body = json.loads(request.content)
        # Model the documented rejection instead of accepting every request shape.
        if any(parameter in body for parameter in ("temperature", "top_p", "top_k", "seed", "thinking")):
            return httpx.Response(
                400, json={"error": {"type": "invalid_request_error", "message": "Unsupported parameter"}}
            )
        payload = anthropic_payload(model="claude-sonnet-5")
        payload["content"].insert(0, {"type": "thinking", "thinking": "", "signature": "offline-signature"})
        return httpx.Response(200, json=payload)

    requests, clients = mock_transport(monkeypatch, provider)
    result = llm_client.generate_answer(
        "Question",
        "Context",
        "System",
        config.ANTHROPIC_MODEL_A,
        api_key="visitor-fixture-key",
        temperature=temperature,
        seed=17,
        max_tokens=2048,
    )
    assert result["status"] == ExecutionStatus.PASSED.value
    assert result["answer"] == "Offline answer."
    assert result["model"] == "claude-sonnet-5"
    assert len(requests) == 1
    assert json.loads(requests[0].content)["max_tokens"] == 2048
    sampling = result["metadata"]["sampling"]
    assert sampling["requested"] == {"temperature": temperature, "seed": 17}
    assert sampling["request_parameters"] == {}
    assert sampling["effective"] == {"temperature": None, "seed": None}
    assert sampling["effective_basis"]["temperature"] == "provider_default_not_reported"
    assert sampling["provider_reported"] is False
    assert result["metadata"]["sampling_request_status"] == "provider_response_received"
    assert "omitted" in result["metadata"]["temperature_warning"]
    assert "omitted" in result["metadata"]["seed_warning"]
    assert result["metadata"]["thinking_configuration"]["documented_default"] == "adaptive"
    assert result["metadata"]["thinking_configuration"]["provider_reported"] is False
    assert result["metadata"]["thinking_configuration"]["output_budget_scope"] == "thinking_and_response_text"
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize("model", ["claude-haiku-4-5", "claude-haiku-4-5-20251001", "claude-3-5-haiku-20241022"])
def test_haiku_retains_supported_temperature_and_omits_unsupported_seed(monkeypatch, model):
    requests, _ = mock_transport(monkeypatch, lambda request: httpx.Response(200, json=anthropic_payload()))
    result = llm_client.generate_answer(
        "Question",
        "Context",
        "System",
        model,
        api_key="visitor-fixture-key",
        temperature=0.35,
        seed=17,
    )
    assert result["status"] == ExecutionStatus.PASSED.value
    body = json.loads(requests[0].content)
    assert body["temperature"] == 0.35
    assert "seed" not in body
    sampling = result["metadata"]["sampling"]
    assert sampling["requested"] == {"temperature": 0.35, "seed": 17}
    assert sampling["request_parameters"] == {"temperature": 0.35}
    assert sampling["effective"] == {"temperature": 0.35, "seed": None}
    assert sampling["effective_basis"]["temperature"] == "request_parameter"
    assert sampling["provider_reported"] is False
    assert "temperature_warning" not in result["metadata"]
    assert "thinking_configuration" not in result["metadata"]


def test_failed_sonnet_request_keeps_sampling_provenance_without_claiming_observed_settings(monkeypatch):
    requests, clients = mock_transport(
        monkeypatch,
        lambda request: httpx.Response(
            500,
            json={"error": {"type": "api_error", "message": "Offline failure"}},
        ),
    )
    result = llm_client.generate_answer(
        "Question",
        "Context",
        "System",
        "claude-sonnet-5",
        api_key="visitor-fixture-key",
        seed=17,
    )
    assert result["status"] == ExecutionStatus.FAILED.value
    assert result["model"] is None
    assert result["metadata"]["sampling_request_status"] == "unconfirmed"
    assert result["metadata"]["sampling"]["requested"] == {"temperature": 0.0, "seed": 17}
    assert result["metadata"]["sampling"]["effective"]["temperature"] is None
    assert result["metadata"]["sampling"]["provider_reported"] is False
    assert "temperature" not in json.loads(requests[0].content)
    assert len(requests) == 1 and clients[0].is_closed


def test_sonnet_thinking_only_exhausted_budget_is_invalid_answer_with_provenance(monkeypatch):
    payload = anthropic_payload(model="claude-sonnet-5")
    payload["usage"] = {"input_tokens": 5, "output_tokens": 2048}
    payload.update(
        {
            "content": [{"type": "thinking", "thinking": "", "signature": "offline-signature"}],
            "stop_reason": "max_tokens",
        }
    )
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
    result = llm_client.generate_answer(
        "Question", "Context", "System", "claude-sonnet-5", api_key="visitor-fixture-key"
    )
    assert result["status"] == ExecutionStatus.INVALID_RESPONSE.value
    assert result["error_code"] == "empty_provider_response"
    assert result["model"] == "claude-sonnet-5"
    assert result["metadata"]["provider_finish_reason"] == "max_tokens"
    assert result["metadata"]["sampling"]["effective"]["temperature"] is None
    assert result["metadata"]["quality_score_eligible"] is False
    assert result["input_tokens"] == 5
    assert result["output_tokens"] == 2048
    assert result["latency_ms"] > 0


def test_empty_haiku_answer_keeps_provider_usage_and_available_cost_estimate(monkeypatch):
    payload = anthropic_payload(model="claude-haiku-4-5")
    payload["content"] = []
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
    result = llm_client.generate_answer(
        "Question", "Context", "System", "claude-haiku-4-5", api_key="visitor-fixture-key"
    )
    assert result["status"] == ExecutionStatus.INVALID_RESPONSE.value
    assert (result["input_tokens"], result["output_tokens"]) == (5, 3)
    assert result["estimated_cost"] == config.estimate_cost_detail("claude-haiku-4-5", 5, 3)["cost"]


@pytest.mark.parametrize(
    "temperature,seed,max_tokens,custom_adapter", [(0.0, None, 2048, False), (0.7, 23, 4096, True)]
)
def test_sonnet_manifest_labels_requested_temperature_and_persists_effective_provenance(
    monkeypatch,
    tmp_path,
    temperature,
    seed,
    max_tokens,
    custom_adapter,
):
    repository = SQLiteRepository(tmp_path / "sampling.sqlite3")
    context = repository.local_context()
    payload = anthropic_payload(model="claude-sonnet-5")
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
    dataset = pd.DataFrame(
        [
            {
                "case_id": "sample",
                "question": "What is the policy?",
                "category": "Policy",
                "expected_behavior": "answer",
                "severity": "medium",
                "tags": ["offline-fixture"],
                "expected_answer": "Offline answer.",
                "expected_source": "Policy",
                "should_escalate": False,
            }
        ]
    )
    chunks = [{"chunk_id": "policy-1", "source_name": "Policy", "chunk_text": "Offline answer."}]
    target = (
        FoundationModelTarget(
            FoundationModelConfig(
                provider="anthropic",
                model="claude-sonnet-5",
                api_key_reference="secret://visitor",
                temperature=temperature,
                seed=seed,
                max_tokens=max_tokens,
            ),
            SecretResolver({"visitor": "visitor-fixture-key"}),
        )
        if custom_adapter
        else None
    )
    with database.request_scope(repository, context):
        rows = run_evaluation(
            dataset,
            chunks,
            {"Current": "Use the policy."},
            "claude-sonnet-5",
            1,
            0.01,
            3500,
            0.03,
            "sampling-fixture",
            api_key="visitor-fixture-key",
            max_concurrency=1,
            target_adapter=target,
        )
    row = rows.iloc[0]
    assert row["execution_status"] == "passed"
    assert row["manifest"]["model"]["temperature"] == temperature
    assert row["manifest"]["model"]["seed"] == seed
    assert row["manifest"]["model"]["token_limit"] == max_tokens
    assert row["manifest"]["model"]["sampling_setting_semantics"] == "requested"
    assert row["manifest"]["model"]["effective_sampling_location"] == "per_execution_result.metadata.sampling"
    assert row["metadata"]["sampling"]["effective"]["temperature"] is None
    assert row["metadata"]["sampling"]["requested"] == {"temperature": temperature, "seed": seed}
    stored_metadata = json.loads(repository.list_results(context)[0]["metadata_json"])
    assert stored_metadata["sampling"] == row["metadata"]["sampling"]
