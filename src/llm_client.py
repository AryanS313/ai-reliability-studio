from __future__ import annotations

import json
import time
from typing import Any

import httpx

from src import config
from src.domain import ExecutionStatus
from src.targets import MockTargetConfig, SyntheticMockTarget

PROVIDER_TIMEOUT_SECONDS = 30.0
SONNET_5_CAPABILITY_SOURCE = "https://platform.claude.com/docs/en/models/sonnet-5/migration-guide"
GEMINI_USAGE_SOURCE = "https://ai.google.dev/gemini-api/docs/generate-content/thinking#pricing"


def _gemini_usage(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate billing counters before the pinned SDK removes newer fields.

    Missing thinking usage is only known to be zero when the reported total
    equals prompt plus candidate usage. Unknown/invalid counts cannot establish
    the complete cost; never infer a thinking budget from answer length.
    """
    counts = {
        key: value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
        for key in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount")
        for value in (raw.get(key),)
    }
    prompt, candidate, thought, total = counts.values()
    thought_source = "provider" if thought is not None else "not_reported"
    if "thoughtsTokenCount" not in raw and prompt is not None and candidate is not None and total == prompt + candidate:
        thought = 0
        thought_source = "reported_total_has_no_unaccounted_tokens"
    output = candidate + thought if candidate is not None and thought is not None else None
    complete = prompt is not None and output is not None
    if "totalTokenCount" in raw and (
        total is None or (prompt is not None and output is not None and total != prompt + output)
    ):
        complete = False
    return {
        "input_tokens": prompt,
        "output_tokens": output,
        "complete": complete,
        "components": {
            "unit": "tokens",
            "prompt": prompt,
            "candidate": candidate,
            "thinking": thought,
            "total": total,
            "thinking_count_source": thought_source,
        },
    }


def _anthropic_sampling_configuration(model_name: str, temperature: float, seed: int | None) -> dict[str, Any]:
    # Scope the exception to the documented model ID; older Haiku models still
    # accept temperature. Do not infer capabilities for unknown future models.
    uses_default_sampling = model_name == "claude-sonnet-5"
    parameters = {} if uses_default_sampling else {"temperature": temperature}
    metadata: dict[str, Any] = {
        "sampling": {
            "policy_version": "anthropic-sampling-v1",
            "requested": {"temperature": temperature, "seed": seed},
            "request_parameters": parameters,
            "effective": {"temperature": None if uses_default_sampling else temperature, "seed": None},
            "effective_basis": {
                "temperature": "provider_default_not_reported" if uses_default_sampling else "request_parameter",
                "seed": "unsupported",
            },
            "provider_reported": False,
        },
        "sampling_request_status": "unconfirmed",
    }
    if uses_default_sampling:
        metadata["sampling"]["capability_source"] = SONNET_5_CAPABILITY_SOURCE
        metadata["temperature_warning"] = (
            f"Claude Sonnet 5 uses provider-default sampling; requested temperature {temperature} was omitted. "
            "The effective numerical temperature is not reported by the provider."
        )
        metadata["thinking_configuration"] = {
            "request_parameter": None,
            "documented_default": "adaptive",
            "default_source": SONNET_5_CAPABILITY_SOURCE,
            "provider_reported": False,
            "output_budget_scope": "thinking_and_response_text",
        }
        metadata["thinking_warning"] = (
            "Claude Sonnet 5 defaults to adaptive thinking. The unchanged max_tokens limit covers thinking "
            "and response text, so thinking can reduce the available answer budget."
        )
    if seed is not None:
        metadata["seed_warning"] = (
            "Provider does not expose a seed parameter for this request; requested seed was omitted."
        )
    return metadata


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
    """Readable normalized role trace; provider wire field names differ."""
    return _normalized_prompt_trace(system_prompt, build_user_message(context, question))


def build_user_message(context: str, question: str) -> str:
    return f"""Retrieved context:
{context.strip() or "No relevant context retrieved."}

User question:
{question}

Assistant answer:"""


def _normalized_prompt_trace(system_prompt: str, user_message: str) -> str:
    messages = ([{"role": "system", "content": system_prompt.strip()}] if system_prompt.strip() else []) + [
        {"role": "user", "content": user_message}
    ]
    return json.dumps({"format": "normalized-role-trace-v1", "messages": messages}, ensure_ascii=False, indent=2)


def _prompt_transport_metadata(provider: str, system_prompt: str) -> dict[str, Any]:
    return {
        "version": "provider-native-system-v2",
        "trace_format": "normalized-role-trace-v1",
        "trace_is_literal_wire_payload": False,
        "system_instruction_location": (
            {"openai": "messages[role=system]", "anthropic": "system", "gemini": "systemInstruction"}[provider]
            if system_prompt.strip()
            else "omitted_empty_instruction"
        ),
        "user_content_location": "contents[role=user]" if provider == "gemini" else "messages[role=user]",
        "request_status": "unconfirmed",
    }


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
    request_metadata = (
        _anthropic_sampling_configuration(model_name, temperature, seed) if provider == "anthropic" else {}
    )
    request_metadata["prompt_transport"] = _prompt_transport_metadata(provider, system_prompt)
    effective_api_key = api_key or config.api_key_for_provider(provider)
    if not effective_api_key:
        return _failure(
            status=ExecutionStatus.INVALID_RESPONSE,
            provider=provider,
            model=model_name,
            code="missing_api_key",
            message=f"No API key is configured for {provider}.",
            final_prompt=final_prompt,
            request_metadata=request_metadata,
        )
    started = time.perf_counter()
    try:
        user_message = build_user_message(context, question)
        if provider == "gemini":
            result = _gemini_answer(
                user_message, model_name, effective_api_key, temperature, seed, max_tokens, system_prompt=system_prompt
            )
        elif provider == "anthropic":
            result = _anthropic_answer(
                user_message, model_name, effective_api_key, temperature, seed, max_tokens, system_prompt=system_prompt
            )
        else:
            result = _openai_answer(
                user_message, model_name, effective_api_key, temperature, seed, max_tokens, system_prompt=system_prompt
            )
        metadata = dict(result.get("metadata") or {})
        metadata["prompt_transport"] = {
            **request_metadata["prompt_transport"],
            "request_status": "provider_response_received",
        }
        result["metadata"] = metadata
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
                request_metadata=request_metadata,
            )
            failure["model"] = _observed_model(result.get("model"))
            for measurement in ("latency_ms", "input_tokens", "output_tokens", "estimated_cost"):
                if measurement in result:
                    failure[measurement] = result[measurement]
            failure["metadata"].update(metadata)
            failure["metadata"]["quality_score_eligible"] = False
            return failure
        result.update({"status": ExecutionStatus.PASSED.value, "provider": provider, "final_prompt": final_prompt})
        return result
    except Exception as exc:  # Provider SDKs expose many optional exception classes.
        failure = _failure(
            status=_provider_status(exc),
            provider=provider,
            model=model_name,
            code=_safe_error_code(exc),
            message=_safe_provider_message(exc),
            final_prompt=final_prompt,
            request_metadata=request_metadata,
        )
        failure["http_status"] = _http_error_status(exc)
        failure["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        failure["metadata"].update(_provider_error_metadata(exc))
        return failure


def _openai_answer(
    prompt: str,
    model_name: str,
    api_key: str,
    temperature: float,
    seed: int | None,
    max_tokens: int,
    *,
    system_prompt: str = "",
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
            "messages": ([{"role": "system", "content": system_prompt.strip()}] if system_prompt.strip() else [])
            + [{"role": "user", "content": prompt}],
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
        _normalized_prompt_trace(system_prompt, prompt),
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
    *,
    system_prompt: str = "",
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
    billing_usage: dict[str, Any] = {}
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
            # google-genai 1.0.0 removes fields absent from its old schema,
            # including thoughtsTokenCount. Preserve only numeric usage here;
            # never persist the raw response or thought content.
            raw = response.json()
            usage = raw.get("usageMetadata") if isinstance(raw, dict) else None
            billing_usage.update(_gemini_usage(usage if isinstance(usage, dict) else {}))
            return HttpResponse(dict(response.headers), [response.text])

        api_client._request = request
        generation = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            seed=seed,
            system_instruction=system_prompt.strip() or None,
        )
        response = client.models.generate_content(model=model_name, contents=prompt, config=generation)
    answer = response.text or ""
    input_tokens = billing_usage.get("input_tokens")
    output_tokens = billing_usage.get("output_tokens")
    result = _result(
        answer,
        model_name,
        _normalized_prompt_trace(system_prompt, prompt),
        start,
        input_tokens,
        output_tokens,
        observed_model=getattr(response, "model_version", None),
    )
    # A word-count estimate omits hidden thinking. Keep available measurements,
    # but do not attribute a complete cost when the provider usage is incomplete.
    result.update({"input_tokens": input_tokens, "output_tokens": output_tokens})
    result["metadata"].update(
        {
            "token_usage_source": "provider" if billing_usage.get("complete") else "incomplete_provider",
            "usage_source": "provider" if billing_usage.get("complete") else "incomplete_provider",
            "usage_components": billing_usage.get("components", {}),
            "output_usage_scope": "candidate_and_thinking_tokens",
            "usage_accounting_version": "gemini-usage-v2",
            "usage_accounting_source": GEMINI_USAGE_SOURCE,
        }
    )
    if not billing_usage.get("complete"):
        result["estimated_cost"] = None
        result["metadata"]["pricing_warning"] = (
            "Gemini token usage is incomplete or inconsistent; total cost is unknown, "
            "including any unreported thinking tokens."
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
    *,
    system_prompt: str = "",
) -> dict[str, Any]:
    from anthropic import NOT_GIVEN, Anthropic

    start = time.perf_counter()
    public = config.public_sessions_enabled()
    sampling_metadata = _anthropic_sampling_configuration(model_name, temperature, seed)
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
            messages=[{"role": "user", "content": prompt}],
            system=system_prompt.strip() or NOT_GIVEN,
            **sampling_metadata["sampling"]["request_parameters"],
        )
    answer = "".join(
        str(getattr(block, "text", "")) for block in response.content if getattr(block, "type", "") == "text"
    )
    input_tokens = getattr(response.usage, "input_tokens", None)
    output_tokens = getattr(response.usage, "output_tokens", None)
    result = _result(
        answer,
        model_name,
        _normalized_prompt_trace(system_prompt, prompt),
        start,
        input_tokens,
        output_tokens,
        observed_model=getattr(response, "model", None),
    )
    result["metadata"]["provider_finish_reason"] = response.stop_reason
    result["metadata"].update(sampling_metadata)
    result["metadata"]["sampling_request_status"] = "provider_response_received"
    if response.stop_reason == "refusal":
        result["metadata"].update({"provider_safety_refusal": True, "provider_refusal_text": answer})
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
    request_metadata: dict[str, Any] | None = None,
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
            **(request_metadata or {}),
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
    status_code = _http_error_status(exc)
    if "timeout" in name or status_code == 408:
        return ExecutionStatus.TIMED_OUT
    if "ratelimit" in name or status_code == 429:
        return ExecutionStatus.RATE_LIMITED
    return ExecutionStatus.FAILED


def _http_error_status(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    if value is None:
        value = getattr(getattr(exc, "response", None), "status_code", None)
    return value if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599 else None


def _provider_error_metadata(exc: Exception) -> dict[str, Any]:
    status_code = _http_error_status(exc)
    if status_code is not None:
        retryable = status_code in {408, 409, 429} or 500 <= status_code <= 599
    else:
        retryable = (
            _provider_status(exc) in {ExecutionStatus.TIMED_OUT, ExecutionStatus.RATE_LIMITED}
            or isinstance(exc, httpx.NetworkError)
            or "connectionerror" in type(exc).__name__.lower()
        )
    metadata: dict[str, Any] = {"retryable": retryable}
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = headers.get("retry-after") if isinstance(headers, httpx.Headers) else None
    if retryable and isinstance(retry_after, str):
        retry_after = retry_after.strip()
        if retry_after.isascii() and retry_after.isdigit() and len(retry_after) <= 3 and int(retry_after) <= 600:
            metadata["retry_after_seconds"] = int(retry_after)
        else:
            # Never replace a longer/unsupported provider wait with a shorter
            # local backoff. Raw header values are deliberately not persisted.
            metadata.update({"retryable": False, "retry_suppressed": "provider_retry_after_not_within_safe_bounds"})
    return metadata


def _safe_error_code(exc: Exception) -> str:
    status = _provider_status(exc)
    status_code = _http_error_status(exc)
    specific = {
        401: "provider_authentication_error",
        403: "provider_permission_denied",
        404: "provider_resource_not_found",
    }.get(status_code or 0)
    if specific:
        return specific
    if status_code is not None and 400 <= status_code < 500 and status_code not in {408, 409, 429}:
        return "provider_invalid_request"
    return {ExecutionStatus.TIMED_OUT: "provider_timeout", ExecutionStatus.RATE_LIMITED: "provider_rate_limit"}.get(
        status, "provider_error"
    )


def _safe_provider_message(exc: Exception) -> str:
    code = _safe_error_code(exc)
    specific = {
        "provider_authentication_error": "The provider rejected authentication. Check this session's API key.",
        "provider_permission_denied": "The provider denied access. Check account permissions, model access, and regional restrictions.",
        "provider_resource_not_found": "The provider could not find the requested model or resource.",
        "provider_invalid_request": "The provider rejected the request parameters. Check the selected model and configuration.",
    }.get(code)
    if specific:
        return specific
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
