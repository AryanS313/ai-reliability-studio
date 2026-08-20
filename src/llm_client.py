from __future__ import annotations

import time
from typing import Any

from src import config
from src.domain import ExecutionStatus
from src.targets import MockTargetConfig, SyntheticMockTarget


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
            return _failure(
                status=ExecutionStatus.INVALID_RESPONSE,
                provider=provider,
                model=model_name,
                code="empty_provider_response",
                message="The provider returned an empty response.",
                final_prompt=final_prompt,
            )
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

    client = OpenAI(api_key=api_key)
    responses_client: Any = client
    start = time.perf_counter()
    try:
        kwargs: dict[str, Any] = {
            "model": model_name,
            "input": prompt,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if seed is not None:
            kwargs["seed"] = seed
        response = responses_client.responses.create(**kwargs)
        answer = response.output_text
        input_tokens = getattr(getattr(response, "usage", None), "input_tokens", None)
        output_tokens = getattr(getattr(response, "usage", None), "output_tokens", None)
    except (AttributeError, TypeError):
        kwargs = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if seed is not None:
            kwargs["seed"] = seed
        response = client.chat.completions.create(**kwargs)
        answer = response.choices[0].message.content or ""
        input_tokens = getattr(response.usage, "prompt_tokens", None) if response.usage else None
        output_tokens = getattr(response.usage, "completion_tokens", None) if response.usage else None
    return _result(answer, model_name, prompt, start, input_tokens, output_tokens)


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

    client = genai.Client(api_key=api_key)
    start = time.perf_counter()
    generation = types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_tokens, seed=seed)
    response = client.models.generate_content(model=model_name, contents=prompt, config=generation)
    answer = response.text or ""
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", None)
    output_tokens = getattr(usage, "candidates_token_count", None)
    return _result(answer, model_name, prompt, start, input_tokens, output_tokens)


def _anthropic_answer(
    prompt: str,
    model_name: str,
    api_key: str,
    temperature: float,
    seed: int | None,
    max_tokens: int,
) -> dict[str, Any]:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    start = time.perf_counter()
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
    result = _result(answer, model_name, prompt, start, input_tokens, output_tokens)
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
) -> dict[str, Any]:
    latency_ms = (time.perf_counter() - started) * 1000
    exact_usage = input_tokens is not None and output_tokens is not None
    input_tokens = input_tokens if input_tokens is not None else config.approx_tokens(prompt)
    output_tokens = output_tokens if output_tokens is not None else config.approx_tokens(answer)
    estimate = config.estimate_cost_detail(model_name, input_tokens, output_tokens)
    return {
        "answer": answer,
        "model": model_name,
        "latency_ms": round(latency_ms, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimate["cost"],
        "metadata": {
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
        "model": model,
        "provider": provider,
        "latency_ms": 0.0,
        "input_tokens": None,
        "output_tokens": None,
        "estimated_cost": None,
        "error_code": code,
        "safe_error": message,
        "final_prompt": final_prompt,
        "metadata": {"quality_score_eligible": False},
    }


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
