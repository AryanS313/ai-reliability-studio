"""Exercise the pinned provider SDKs over HTTPX MockTransport, never provider APIs."""

from __future__ import annotations

import json
import socket

import httpx
import pytest

from src import config, llm_client
from src.domain import ExecutionStatus
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
