from __future__ import annotations

import json
import time
from typing import Any

import httpx

from src import config
from src.domain import ExecutionStatus
from src.targets import MockTargetConfig, SyntheticMockTarget

PROVIDER_TIMEOUT_SECONDS = 30.0


def _http_client(*, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    # Explicit clients avoid the pinned SDKs' obsolete httpx `proxies` argument.
    # Anonymous visitors must never inherit the deployment owner's proxy settings.
    return httpx.Client(
        timeout=httpx.Timeout(PROVIDER_TIMEOUT_SECONDS, connect=10.0),
        follow_redirects=False,
        trust_env=not config.public_sessions_enabled(),
        transport=transport,
    )


def build_final_prompt(system_prompt: str, context: str, question: str) -> str:
    return f"""{system_prompt.strip()}

Retrieved context:
{context.strip() or "No relevant context retrieved."}

User question:
{question}

Assistant answer:"""


def generate_answer(
    question: str,
    context: str,
    system_prompt: str,
    model_name: str,
    api_key: str | None = None,
    *,
    temperature: float = 0.0,
    seed: int | None = None,
    max_tokens: int = 2048,
    mock_scenario: str = "correct_grounded_answer",
    retrieved_chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    final_prompt = build_final_prompt(system_prompt, context, question)
    if model_name == "mock-model":
        response = SyntheticMockTarget(MockTargetConfig(scenario=mock_scenario)).execute(
            {
                "question": question,
                "retrieved_chunks": retrieved_chunks or _context_chunk(context),
                "mock_scenario": mock_scenario,
            }
        )
        return {
            "status": response.status.value,
            "answer": response.answer,
            "model": "mock-model",
            "provider": "synthetic",
            "latency_ms": response.latency_ms,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "estimated_cost": 0.0,
            "metadata": response.metadata,
            "escalation": response.escalation,
            "citations": list(response.citations),
            "final_prompt": final_prompt,
        }

    provider = config.provider_for_model(model_name)
    effective_api_key = api_key or config.api_key_for_provider(provider)
    if not effective_api_key:
        return _failure(
            status=ExecutionStatus.INVALID_RESPONSE,
            provider=provider,
            model=model_name,
            code="missing_api_key",
            message=f"No API key is configured for {provider}.",
            final_prompt=final_prompt,
        )
    try:
        if provider == "gemini":
            result = _gemini_answer(final_prompt, model_name, effective_api_key, temperature, seed, max_tokens)
        elif provider == "anthropic":
            result = _anthropic_answer(final_prompt, model_name, effective_api_key, temperature, seed, max_tokens)
        else:
            result = _openai_answer(final_prompt, model_name, effective_api_key, temperature, seed, max_tokens)
        metadata = dict(result.get("metadata") or {})
        if result.get("refusal") or metadata.get("provider_safety_refusal"):
            metadata["provider_safety_refusal"] = True
            result["metadata"] = metadata
        if not str(result.get("answer") or "").strip() and not metadata.get("provider_safety_refusal"):
            failure = _failure(
                status=ExecutionStatus.INVALID_RESPONSE,
                provider=provider,
                model=model_name,
                code="empty_provider_response",
                message="The provider returned an empty response.",
                final_prompt=final_prompt,
            )
            failure["model"] = _observed_model(result.get("model"))
            failure["metadata"].update(metadata)
            failure["metadata"]["quality_score_eligible"] = False
            return failure
        result.update({"status": ExecutionStatus.PASSED.value, "provider": provider, "final_prompt": final_prompt})
        return result
    except Exception as exc:  # Provider SDKs expose many optional exception classes.
        return _failure(
            status=_provider_status(exc),
            provider=provider,
            model=model_name,
            code=_safe_error_code(exc),
            message=_safe_provider_message(exc),
            final_prompt=final_prompt,
        )


def _openai_answer(
    prompt: str,
    model_name: str,
    api_key: str,
    temperature: float,
    seed: int | None,
    max_tokens: int,
) -> dict[str, Any]:
    from openai import OpenAI

    start = time.perf_counter()
    public = config.public_sessions_enabled()
    with (
        _http_client() as http_client,
        OpenAI(
            api_key=api_key,
            base_url="https://api.openai.com/v1" if public else None,
            organization="" if public else None,
            project="" if public else None,
            http_client=http_client,
            timeout=http_client.timeout,
            max_retries=0,
        ) as client,
    ):
        if public:
            # Empty explicit arguments prevent environment fallback at construction;
            # None here also omits the optional headers from the actual request.
            client.organization = None
            client.project = None
        # OpenAI 1.54.4 exposes Chat Completions; it has no Responses resource.
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if seed is not None:
            kwargs["seed"] = seed
        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        refusal = getattr(message, "refusal", None)
        answer = message.content or refusal or ""
        input_tokens = getattr(response.usage, "prompt_tokens", None) if response.usage else None
        output_tokens = getattr(response.usage, "completion_tokens", None) if response.usage else None
    result = _result(
        answer,
        model_name,
        prompt,
        start,
        input_tokens,
        output_tokens,
        observed_model=getattr(response, "model", None),
    )
    result["metadata"]["provider_finish_reason"] = response.choices[0].finish_reason
    if refusal or response.choices[0].finish_reason == "content_filter":
        result["metadata"].update({"provider_safety_refusal": True, "provider_refusal_text": refusal})
    return result


def _gemini_answer(
    prompt: str,
    model_name: str,
    api_key: str,
    temperature: float,
    seed: int | None,
    max_tokens: int,
) -> dict[str, Any]:
    from google import genai
    from google.genai import types
    from google.genai._api_client import HttpResponse
    from google.genai.client import DebugConfig

    start = time.perf_counter()
    public = config.public_sessions_enabled()
    options: dict[str, Any] = {"timeout": int(PROVIDER_TIMEOUT_SECONDS * 1000)}
    if public:
        options["base_url"] = "https://generativelanguage.googleapis.com/"
    client = genai.Client(
        api_key=api_key,
        vertexai=False if public else None,
        http_options=options,
        debug_config=DebugConfig(client_mode=None, replays_directory=None, replay_id=None),
    )
    api_client: Any = client._api_client
    if public:
        api_client.project = None
        api_client.location = None
        api_client._credentials = None
    # google-genai 1.0.0 has no custom transport option and its requests sessions
    # inherit proxies/netrc and are not closed. Keep the SDK serialization/parser,
    # but use a per-instance synchronous transport with an explicit lifetime.
    with _http_client() as http_client:

        def request(http_request: Any, stream: bool = False) -> Any:
            if stream:
                raise ValueError("Streaming is not supported by this adapter.")
            response = http_client.request(
                method=http_request.method,
                url=http_request.url,
                headers=http_request.headers,
                content=json.dumps(http_request.data),
            )
            response.raise_for_status()
            return HttpResponse(dict(response.headers), [response.text])

        api_client._request = request
        generation = types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_tokens, seed=seed)
        response = client.models.generate_content(model=model_name, contents=prompt, config=generation)
    answer = response.text or ""
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", None)
    output_tokens = getattr(usage, "candidates_token_count", None)
    result = _result(
        answer,
        model_name,
        prompt,
        start,
        input_tokens,
        output_tokens,
        observed_model=getattr(response, "model_version", None),
    )
    reasons = [_enum_value(getattr(candidate, "finish_reason", None)) for candidate in response.candidates or []]
    feedback = getattr(response, "prompt_feedback", None)
    block_reason = _enum_value(getattr(feedback, "block_reason", None))
    result["metadata"].update(
        {
            "provider_finish_reasons": reasons,
            "provider_block_reason": block_reason,
            "provider_block_reason_message": getattr(feedback, "block_reason_message", None),
            "provider_prompt_safety_ratings": [
                rating.model_dump(mode="json", exclude_none=True)
                for rating in getattr(feedback, "safety_ratings", None) or []
            ],
            "provider_candidate_safety_ratings": [
                [rating.model_dump(mode="json", exclude_none=True) for rating in candidate.safety_ratings or []]
                for candidate in response.candidates or []
            ],
        }
    )
    if block_reason not in (None, "BLOCKED_REASON_UNSPECIFIED") or any(
        reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY"}
        for reason in reasons
    ):
        result["metadata"]["provider_safety_refusal"] = True
    return result


def _anthropic_answer(
    prompt: str,
    model_name: str,
    api_key: str,
    temperature: float,
    seed: int | None,
    max_tokens: int,
) -> dict[str, Any]:
    from anthropic import Anthropic

    start = time.perf_counter()
    public = config.public_sessions_enabled()
    with (
        _http_client() as http_client,
        Anthropic(
            api_key=api_key,
            auth_token="" if public else None,
            base_url="https://api.anthropic.com" if public else None,
            http_client=http_client,
            timeout=http_client.timeout,
            max_retries=0,
        ) as client,
    ):
        response = client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
    answer = "".join(
        str(getattr(block, "text", "")) for block in response.content if getattr(block, "type", "") == "text"
    )
    input_tokens = getattr(response.usage, "input_tokens", None)
    output_tokens = getattr(response.usage, "output_tokens", None)
    result = _result(
        answer,
        model_name,
        prompt,
        start,
        input_tokens,
        output_tokens,
        observed_model=getattr(response, "model", None),
    )
    result["metadata"]["provider_finish_reason"] = response.stop_reason
    if response.stop_reason == "refusal":
        result["metadata"].update({"provider_safety_refusal": True, "provider_refusal_text": answer})
    if seed is not None:
        result.setdefault("metadata", {})["seed_warning"] = (
            "Provider does not expose a seed parameter for this request."
        )
    return result


def _result(
    answer: str,
    model_name: str,
    prompt: str,
    started: float,
    input_tokens: int | None,
    output_tokens: int | None,
    *,
    observed_model: Any = None,
) -> dict[str, Any]:
    latency_ms = (time.perf_counter() - started) * 1000
    exact_usage = input_tokens is not None and output_tokens is not None
    input_tokens = input_tokens if input_tokens is not None else config.approx_tokens(prompt)
    output_tokens = output_tokens if output_tokens is not None else config.approx_tokens(answer)
    estimate = config.estimate_cost_detail(model_name, input_tokens, output_tokens)
    return {
        "answer": answer,
        "model": _observed_model(observed_model),
        "latency_ms": round(latency_ms, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimate["cost"],
        "metadata": {
            "requested_model": model_name,
            "model_identity_provenance": "provider_response" if _observed_model(observed_model) else "not_reported",
            "pricing_model": model_name,
            "pricing_model_source": "requested_model_estimate",
            "token_usage_source": "provider" if exact_usage else "estimated",
            "pricing_version": estimate["pricing_version"],
            "pricing_source": estimate["pricing_source"],
            "pricing_effective_date": estimate["pricing_effective_date"],
            "pricing_expires_on": estimate["pricing_expires_on"],
            "pricing_warning": estimate["warning"],
        },
    }


def _failure(
    *,
    status: ExecutionStatus,
    provider: str,
    model: str,
    code: str,
    message: str,
    final_prompt: str,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "answer": "",
        "model": None,
        "provider": provider,
        "latency_ms": 0.0,
        "input_tokens": None,
        "output_tokens": None,
        "estimated_cost": None,
        "error_code": code,
        "safe_error": message,
        "final_prompt": final_prompt,
        "metadata": {
            "quality_score_eligible": False,
            "requested_model": model,
            "model_identity_provenance": "not_reported",
        },
    }


def _observed_model(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _enum_value(value: Any) -> str | None:
    return str(getattr(value, "value", value)) if value is not None else None


def _provider_status(exc: Exception) -> ExecutionStatus:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message:
        return ExecutionStatus.TIMED_OUT
    if "ratelimit" in name or "rate limit" in message or "429" in message:
        return ExecutionStatus.RATE_LIMITED
    return ExecutionStatus.FAILED


def _safe_error_code(exc: Exception) -> str:
    status = _provider_status(exc)
    return {ExecutionStatus.TIMED_OUT: "provider_timeout", ExecutionStatus.RATE_LIMITED: "provider_rate_limit"}.get(
        status, "provider_error"
    )


def _safe_provider_message(exc: Exception) -> str:
    status = _provider_status(exc)
    if status == ExecutionStatus.TIMED_OUT:
        return "The provider did not respond before the configured timeout."
    if status == ExecutionStatus.RATE_LIMITED:
        return "The provider rate limit was reached. The request may be retried."
    return "The provider request failed. Sensitive provider details were withheld."


def _context_chunk(context: str) -> list[dict[str, Any]]:
    return (
        [{"chunk_text": context, "source_name": "Provided Context", "chunk_id": "context-0"}] if context.strip() else []
    )
