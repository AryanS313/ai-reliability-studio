from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from src import config
from src.domain import SYNTHETIC_EVIDENCE_NOTICE, ExecutionStatus, TargetResponse, TargetType
from src.utils import keyword_tokens
from src.versioning import version_hash


class TargetConfigurationError(ValueError):
    pass


class SecretResolver:
    """Resolves references at execution time; secret values are never serialized."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = dict(values or {})

    def resolve(self, reference: str) -> str:
        if not reference.startswith("secret://"):
            raise TargetConfigurationError("Secret values must use a secret://NAME reference")
        name = reference.removeprefix("secret://")
        value = self._values.get(name) or os.getenv(name, "")
        if not value:
            raise TargetConfigurationError(f"Secret reference {name!r} is not configured")
        return value


class TargetAdapter(ABC):
    target_type: TargetType

    @property
    @abstractmethod
    def version(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def execute(self, request: dict[str, Any]) -> TargetResponse:
        raise NotImplementedError

    def health_check(self) -> TargetResponse:
        return TargetResponse(status=ExecutionStatus.PASSED, metadata={"health": "available"})


@dataclass(frozen=True)
class MockTargetConfig:
    scenario: str = "correct_grounded_answer"
    seed: int = 17
    scenario_version: str = "synthetic-scenarios-v2"


class SyntheticMockTarget(TargetAdapter):
    target_type = TargetType.SYNTHETIC
    SCENARIOS = {
        "correct_grounded_answer",
        "hallucination",
        "refusal",
        "escalation",
        "unsupported_answer",
        "contradiction",
        "citation_failure",
        "missed_escalation",
        "provider_error",
        "timeout",
        "malformed_response",
        "rate_limiting",
        "privacy_leakage",
        "retrieval_failure",
    }

    def __init__(self, configuration: MockTargetConfig | None = None) -> None:
        self.configuration = configuration or MockTargetConfig()
        if self.configuration.scenario not in self.SCENARIOS:
            raise TargetConfigurationError(f"Unknown mock scenario: {self.configuration.scenario}")

    @property
    def version(self) -> str:
        return version_hash({"type": self.target_type.value, **asdict(self.configuration)})

    def execute(self, request: dict[str, Any]) -> TargetResponse:
        started = time.perf_counter()
        scenario = str(request.get("mock_scenario") or self.configuration.scenario)
        if scenario not in self.SCENARIOS:
            scenario = self.configuration.scenario
        if scenario == "provider_error":
            return TargetResponse(
                status=ExecutionStatus.FAILED,
                provider="synthetic",
                model="mock-model",
                error_code="synthetic_provider_error",
                safe_error="Synthetic provider failure scenario.",
                metadata=self._metadata(scenario),
            )
        if scenario == "rate_limiting":
            return TargetResponse(
                status=ExecutionStatus.RATE_LIMITED,
                provider="synthetic",
                model="mock-model",
                error_code="synthetic_rate_limit",
                safe_error="Synthetic rate-limit scenario.",
                metadata=self._metadata(scenario),
            )
        if scenario == "timeout":
            return TargetResponse(
                status=ExecutionStatus.TIMED_OUT,
                provider="synthetic",
                model="mock-model",
                error_code="synthetic_timeout",
                safe_error="Synthetic timeout scenario.",
                metadata=self._metadata(scenario),
            )
        if scenario == "malformed_response":
            return TargetResponse(
                status=ExecutionStatus.INVALID_RESPONSE,
                provider="synthetic",
                model="mock-model",
                error_code="synthetic_malformed_response",
                safe_error="Synthetic malformed-response scenario.",
                metadata=self._metadata(scenario),
            )
        question = str(request.get("question") or request.get("input") or "")
        chunks = list(request.get("retrieved_chunks") or [])
        sentence, chunk = _best_grounded_sentence(question, chunks)
        if not sentence:
            sentence = "The available context does not contain enough information to answer this request."
            chunk = {}
        citation = _citation(chunk)
        escalation_expected = bool(request.get("should_escalate", False))
        reference_answers = request.get("expected_answers") or []
        reference_answer = str(
            request.get("expected_answer")
            or (reference_answers[0] if isinstance(reference_answers, list) and reference_answers else "")
        ).strip()
        if scenario == "correct_grounded_answer" and reference_answer:
            answer = reference_answer
            chunk = _best_evidence_chunk(
                reference_answer,
                chunks,
                expected_sources=request.get("expected_sources") or [],
            )
        elif scenario in {"unsupported_answer", "hallucination"}:
            answer = "This request is automatically approved and will complete within 24 hours."
        elif scenario == "contradiction":
            answer = _invert_claim(sentence)
        elif scenario == "refusal":
            answer = (
                "I cannot complete that request from the available evidence. Please contact an authorized reviewer."
            )
            chunk = {}
        elif scenario == "privacy_leakage":
            answer = "The customer's payment card is 4242 4242 4242 4242."
            chunk = {}
        elif scenario == "retrieval_failure":
            answer = "I do not have enough retrieved evidence to answer this request."
            chunk = {}
        else:
            answer = sentence
        if scenario != "citation_failure" and chunk:
            answer = f"{answer}\nCitation: [source:{citation['source_name']} chunk:{citation['chunk_id']}]"
        escalation = {
            "should_escalate": (
                False if scenario == "missed_escalation" else True if scenario == "escalation" else escalation_expected
            ),
            "destination": request.get("escalation_destination") or ("support" if escalation_expected else None),
            "reason": "Synthetic structured decision for workflow demonstration.",
            "urgency": request.get("escalation_urgency") or "normal",
        }
        latency = (time.perf_counter() - started) * 1000 + 10
        return TargetResponse(
            status=ExecutionStatus.PASSED,
            answer=answer,
            citations=(citation,) if chunk and scenario != "citation_failure" else (),
            escalation=escalation,
            latency_ms=round(latency, 2),
            input_tokens=config.approx_tokens(question + " ".join(str(item.get("chunk_text", "")) for item in chunks)),
            output_tokens=config.approx_tokens(answer),
            cost=0.0,
            provider="synthetic",
            model="mock-model",
            metadata=self._metadata(scenario),
        )

    def _metadata(self, scenario: str) -> dict[str, Any]:
        return {
            "target_type": self.target_type.value,
            "scenario": scenario,
            "scenario_version": self.configuration.scenario_version,
            "synthetic": True,
            "prompt_content_ignored": True,
            "reference_answer_fixture": scenario == "correct_grounded_answer",
            "prompt_notice": "Synthetic scenarios use deterministic responses and do not evaluate prompt quality.",
            "evidence_notice": SYNTHETIC_EVIDENCE_NOTICE,
        }


@dataclass(frozen=True)
class FoundationModelConfig:
    provider: str
    model: str
    api_key_reference: str
    temperature: float = 0.0
    seed: int | None = None
    max_tokens: int = 2048


class FoundationModelTarget(TargetAdapter):
    target_type = TargetType.FOUNDATION_MODEL

    def __init__(self, configuration: FoundationModelConfig, secrets: SecretResolver | None = None) -> None:
        self.configuration = configuration
        self.secrets = secrets or SecretResolver()

    @property
    def version(self) -> str:
        # The reference name is reproducible; the secret value is deliberately absent.
        return version_hash({"type": self.target_type.value, **asdict(self.configuration)})

    def execute(self, request: dict[str, Any]) -> TargetResponse:
        from src.llm_client import generate_answer

        api_key = self.secrets.resolve(self.configuration.api_key_reference)
        result = generate_answer(
            question=str(request.get("question") or request.get("input") or ""),
            context=str(request.get("context") or ""),
            system_prompt=str(request.get("system_prompt") or ""),
            model_name=self.configuration.model,
            api_key=api_key,
            temperature=self.configuration.temperature,
            seed=self.configuration.seed,
            max_tokens=self.configuration.max_tokens,
        )
        return TargetResponse(
            status=ExecutionStatus(result.get("status", ExecutionStatus.PASSED.value)),
            answer=str(result.get("answer", "")),
            latency_ms=float(result.get("latency_ms", 0)),
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
            cost=result.get("estimated_cost"),
            metadata=dict(result.get("metadata") or {}),
            error_code=result.get("error_code"),
            safe_error=result.get("safe_error"),
            provider=self.configuration.provider,
            model=self.configuration.model,
            final_prompt=str(result.get("final_prompt", "")),
        )


@dataclass(frozen=True)
class ExternalTargetConfig:
    name: str
    endpoint: str
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    request_template: dict[str, Any] = field(default_factory=lambda: {"input": "${question}"})
    response_mappings: dict[str, str] = field(default_factory=lambda: {"answer": "$.answer"})
    timeout_seconds: float = 30.0
    retry_count: int = 2
    streaming: bool = False
    health_check_path: str | None = None

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        host = (parsed.hostname or "").lower()
        if not host or parsed.username or parsed.password:
            raise TargetConfigurationError(
                "External target endpoint must have a valid host and no embedded credentials"
            )
        private_host = _is_private_host(host)
        loopback_host = _is_loopback_host(host)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and loopback_host and config.APP_ENV != "production"
        ):
            raise TargetConfigurationError("External endpoints must use HTTPS; local HTTP is development-only")
        if config.APP_ENV == "production" and not config.EXTERNAL_TARGET_ALLOWED_HOSTS:
            raise TargetConfigurationError("Production external targets require EXTERNAL_TARGET_ALLOWED_HOSTS")
        if config.EXTERNAL_TARGET_ALLOWED_HOSTS and host not in config.EXTERNAL_TARGET_ALLOWED_HOSTS:
            raise TargetConfigurationError("External target host is not in EXTERNAL_TARGET_ALLOWED_HOSTS")
        if private_host and config.APP_ENV == "production" and not config.ALLOW_PRIVATE_EXTERNAL_TARGETS:
            raise TargetConfigurationError("Private-network external targets are disabled in production")
        if self.method.upper() not in {"GET", "POST", "PUT", "PATCH"}:
            raise TargetConfigurationError("External target method must be GET, POST, PUT, or PATCH")
        if not 0.1 <= self.timeout_seconds <= 300:
            raise TargetConfigurationError("timeout_seconds must be between 0.1 and 300")
        for value in self.headers.values():
            if _looks_like_secret(value) and not value.startswith("secret://"):
                raise TargetConfigurationError("Header secrets must be stored as secret://NAME references")


class ExternalHTTPTarget(TargetAdapter):
    target_type = TargetType.EXTERNAL_API

    def __init__(
        self,
        configuration: ExternalTargetConfig,
        secrets: SecretResolver | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.configuration = configuration
        self.secrets = secrets or SecretResolver()
        self._opener = opener or _secure_urlopen

    @property
    def version(self) -> str:
        return version_hash({"type": self.target_type.value, **asdict(self.configuration)})

    def execute(self, request: dict[str, Any]) -> TargetResponse:
        started = time.perf_counter()
        try:
            _validate_resolved_destination(self.configuration.endpoint)
        except TargetConfigurationError:
            return TargetResponse(
                status=ExecutionStatus.INVALID_RESPONSE,
                error_code="external_destination_blocked",
                safe_error="The external target destination failed network safety validation.",
                provider="external",
            )
        headers = {name: self._header_value(value) for name, value in self.configuration.headers.items()}
        headers.setdefault("Content-Type", "application/json")
        payload = _render_template(self.configuration.request_template, request)
        body = None if self.configuration.method.upper() == "GET" else json.dumps(payload).encode("utf-8")
        if body is not None and len(body) > config.MAX_EXTERNAL_REQUEST_BYTES:
            return TargetResponse(
                status=ExecutionStatus.INVALID_RESPONSE,
                error_code="external_request_too_large",
                safe_error="The rendered external target request exceeds the configured size limit.",
                provider="external",
            )
        http_request = urllib.request.Request(  # noqa: S310 - ExternalTargetConfig restricts schemes to HTTPS or loopback HTTP
            self.configuration.endpoint,
            data=body,
            headers=headers,
            method=self.configuration.method.upper(),
        )
        try:
            response = self._opener(http_request, timeout=self.configuration.timeout_seconds)
            status_code = int(getattr(response, "status", 200))
            final_url_getter = getattr(response, "geturl", None)
            final_url = str(final_url_getter()) if callable(final_url_getter) else self.configuration.endpoint
            if not _same_origin(self.configuration.endpoint, final_url):
                return TargetResponse(
                    status=ExecutionStatus.INVALID_RESPONSE,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    http_status=status_code,
                    error_code="external_redirect_blocked",
                    safe_error="The external target attempted a cross-origin redirect, which was blocked.",
                    provider="external",
                )
            if 300 <= status_code < 400:
                return TargetResponse(
                    status=ExecutionStatus.INVALID_RESPONSE,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    http_status=status_code,
                    error_code="external_redirect_blocked",
                    safe_error="External target redirects are disabled.",
                    provider="external",
                )
            if status_code >= 400:
                rate_limited = status_code == 429
                authentication_error = status_code in {401, 403}
                return TargetResponse(
                    status=ExecutionStatus.RATE_LIMITED if rate_limited else ExecutionStatus.FAILED,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    http_status=status_code,
                    error_code=(
                        "rate_limited"
                        if rate_limited
                        else "external_authentication_error"
                        if authentication_error
                        else "external_http_error"
                    ),
                    safe_error=f"External target returned HTTP {status_code}.",
                    provider="external",
                )
            try:
                response_bytes = response.read(config.MAX_EXTERNAL_RESPONSE_BYTES + 1)
            except TypeError:  # Minimal test/dummy responses may not expose read(size).
                response_bytes = response.read()
            if len(response_bytes) > config.MAX_EXTERNAL_RESPONSE_BYTES:
                return TargetResponse(
                    status=ExecutionStatus.INVALID_RESPONSE,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    http_status=status_code,
                    error_code="external_response_too_large",
                    safe_error="The external target response exceeds the configured size limit.",
                    provider="external",
                )
            raw = response_bytes.decode("utf-8", errors="replace")
            data = _parse_stream(raw) if self.configuration.streaming else json.loads(raw)
        except TimeoutError:
            return TargetResponse(
                status=ExecutionStatus.TIMED_OUT,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code="target_timeout",
                safe_error="The external target did not respond before the configured timeout.",
                provider="external",
            )
        except urllib.error.HTTPError as exc:
            status_code = int(exc.code)
            if 300 <= status_code < 400:
                return TargetResponse(
                    status=ExecutionStatus.INVALID_RESPONSE,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    http_status=status_code,
                    error_code="external_redirect_blocked",
                    safe_error="External target redirects are disabled.",
                    provider="external",
                )
            status = ExecutionStatus.RATE_LIMITED if status_code == 429 else ExecutionStatus.FAILED
            return TargetResponse(
                status=status,
                latency_ms=(time.perf_counter() - started) * 1000,
                http_status=status_code,
                error_code=(
                    "rate_limited"
                    if status_code == 429
                    else "external_authentication_error"
                    if status_code in {401, 403}
                    else "external_http_error"
                ),
                safe_error=f"External target returned HTTP {status_code}.",
                provider="external",
            )
        except (urllib.error.URLError, json.JSONDecodeError, UnicodeError):
            return TargetResponse(
                status=ExecutionStatus.INVALID_RESPONSE,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_code="invalid_external_response",
                safe_error="External target response could not be validated.",
                provider="external",
            )
        mappings = self.configuration.response_mappings
        answer = _json_path(data, mappings.get("answer", "$.answer"))
        if not isinstance(answer, str) or not answer.strip():
            return TargetResponse(
                status=ExecutionStatus.INVALID_RESPONSE,
                latency_ms=(time.perf_counter() - started) * 1000,
                http_status=status_code,
                error_code="missing_answer",
                safe_error="The configured answer mapping did not produce non-empty text.",
                provider="external",
            )
        citations = _as_tuple_of_dicts(_json_path(data, mappings.get("citations", "")))
        tool_calls = _as_tuple_of_dicts(_json_path(data, mappings.get("tool_calls", "")))
        escalation = _json_path(data, mappings.get("escalation", ""))
        metadata = _json_path(data, mappings.get("metadata", ""))
        return TargetResponse(
            status=ExecutionStatus.PASSED,
            answer=answer,
            citations=citations,
            tool_calls=tool_calls,
            escalation=escalation if isinstance(escalation, dict) else None,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            http_status=status_code,
            input_tokens=_optional_int(_json_path(data, mappings.get("input_tokens", ""))),
            output_tokens=_optional_int(_json_path(data, mappings.get("output_tokens", ""))),
            cost=_optional_float(_json_path(data, mappings.get("cost", ""))),
            metadata=metadata if isinstance(metadata, dict) else {},
            provider="external",
            model=str(_json_path(data, mappings.get("model", "")) or "external-assistant"),
        )

    def health_check(self) -> TargetResponse:
        if not self.configuration.health_check_path:
            return super().health_check()
        endpoint = self.configuration.endpoint.rstrip("/") + "/" + self.configuration.health_check_path.lstrip("/")
        try:
            headers = {name: self._header_value(value) for name, value in self.configuration.headers.items()}
            response = self._opener(
                urllib.request.Request(  # noqa: S310 - endpoint inherits validated target origin
                    endpoint, headers=headers, method="GET"
                ),
                timeout=min(10, self.configuration.timeout_seconds),
            )
            status = int(getattr(response, "status", 200))
            return TargetResponse(
                status=ExecutionStatus.PASSED if status < 400 else ExecutionStatus.FAILED, http_status=status
            )
        except Exception:
            return TargetResponse(
                status=ExecutionStatus.FAILED,
                error_code="health_check_failed",
                safe_error="External target health check failed.",
            )

    def _header_value(self, value: str) -> str:
        if value.startswith("secret://"):
            return self.secrets.resolve(value)
        return value


def target_configuration_for_storage(configuration: Any) -> dict[str, Any]:
    value = asdict(configuration)
    # Reject accidental raw credentials in all serializable fields.
    serialized = json.dumps(value)
    if re.search(r"(?:sk-|api[_-]?key\s*[:=]\s*[A-Za-z0-9])", serialized, re.I):
        raise TargetConfigurationError("Raw secrets cannot be stored in target configuration")
    value["version_hash"] = version_hash(value)
    return value


def _best_grounded_sentence(question: str, chunks: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    question_tokens = keyword_tokens(question)
    best: tuple[float, str, dict[str, Any]] | None = None
    for chunk in chunks:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(chunk.get("chunk_text", ""))):
            sentence = sentence.strip(" #\t")
            tokens = keyword_tokens(sentence)
            if len(tokens) < 2:
                continue
            score = len(tokens & question_tokens) / max(1, len(question_tokens))
            if best is None or score > best[0]:
                best = (score, sentence, chunk)
    return (best[1], best[2]) if best else ("", {})


def _best_evidence_chunk(
    reference_answer: str,
    chunks: list[dict[str, Any]],
    *,
    expected_sources: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    expected = {str(source).strip().casefold() for source in expected_sources if str(source).strip()}
    matching = [chunk for chunk in chunks if str(chunk.get("source_name") or "").strip().casefold() in expected]
    candidates = matching or chunks
    reference_tokens = keyword_tokens(reference_answer)
    best: tuple[float, dict[str, Any]] | None = None
    for chunk in candidates:
        tokens = keyword_tokens(str(chunk.get("chunk_text") or ""))
        score = len(tokens & reference_tokens) / max(1, len(reference_tokens))
        if best is None or score > best[0]:
            best = (score, chunk)
    return best[1] if best and best[0] > 0 else {}


def _citation(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": str(chunk.get("document_id", chunk.get("filename", ""))),
        "document_version": str(chunk.get("document_version", chunk.get("document_hash", "legacy"))),
        "page": chunk.get("page"),
        "section": chunk.get("section"),
        "chunk_id": str(chunk.get("chunk_id", chunk.get("id", f"chunk-{chunk.get('chunk_index', 0)}"))),
        "text_start": chunk.get("text_start"),
        "text_end": chunk.get("text_end"),
        "source_name": str(chunk.get("source_name", chunk.get("filename", "Unknown Source"))),
    }


def _invert_claim(sentence: str) -> str:
    replacements = [
        (r"\bnot\s+eligible\b", "eligible"),
        (r"\bineligible\b", "eligible"),
        (r"\bcannot\b", "can"),
        (r"\bmust\s+not\b", "may"),
        (r"\bnot\s+allowed\b", "allowed"),
        (r"\bblocked\b", "allowed"),
        (r"\brequires?\b", "does not require"),
    ]
    for pattern, replacement in replacements:
        changed, count = re.subn(pattern, replacement, sentence, count=1, flags=re.I)
        if count:
            return changed
    for pattern, replacement in [
        (r"\beligible\b", "not eligible"),
        (r"\bcan\b", "cannot"),
        (r"\ballowed\b", "not allowed"),
    ]:
        changed, count = re.subn(pattern, replacement, sentence, count=1, flags=re.I)
        if count:
            return changed
    return f"It is not true that {sentence[0].lower() + sentence[1:]}" if sentence else "The context is incorrect."


def _render_template(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render_template(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_template(item, variables) for item in value]
    if isinstance(value, str):
        exact = re.fullmatch(r"\$\{([A-Za-z0-9_.-]+)\}", value)
        if exact:
            return variables.get(exact.group(1))
        return re.sub(r"\$\{([A-Za-z0-9_.-]+)\}", lambda match: str(variables.get(match.group(1), "")), value)
    return value


def _json_path(value: Any, path: str) -> Any:
    if not path:
        return None
    if path == "$":
        return value
    if not path.startswith("$."):
        raise TargetConfigurationError(f"JSON path must begin with $.: {path}")
    current = value
    for part in path[2:].split("."):
        match = re.fullmatch(r"([^\[]+)(?:\[(\d+)\])?", part)
        if not match or not isinstance(current, dict):
            return None
        current = current.get(match.group(1))
        if match.group(2) is not None:
            if not isinstance(current, list):
                return None
            index = int(match.group(2))
            current = current[index] if index < len(current) else None
    return current


def _parse_stream(raw: str) -> dict[str, Any]:
    events = []
    for line in raw.splitlines():
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload and payload != "[DONE]":
                events.append(json.loads(payload))
    if not events:
        return json.loads(raw)
    if all(isinstance(event, dict) and isinstance(event.get("answer"), str) for event in events):
        merged = dict(events[-1])
        merged["answer"] = "".join(event["answer"] for event in events)
        return merged
    return events[-1]


def _as_tuple_of_dicts(value: Any) -> tuple[dict[str, Any], ...]:
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, dict))
    if isinstance(value, dict):
        return (value,)
    return ()


def _looks_like_secret(value: str) -> bool:
    lowered = value.lower()
    return bool(
        value.startswith(("sk-", "Bearer "))
        or "api_key" in lowered
        or "token=" in lowered
        or (len(value) > 32 and " " not in value)
    )


def _is_private_host(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved)


def _is_loopback_host(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _validate_resolved_destination(endpoint: str) -> None:
    """Block DNS-resolved private destinations in production to reduce SSRF/rebinding risk."""
    if config.APP_ENV != "production":
        return
    host = (urlparse(endpoint).hostname or "").lower()
    if not host:
        raise TargetConfigurationError("External target destination has no host")
    try:
        addresses = {
            str(item[4][0]).split("%")[0]
            for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if item and item[4]
        }
    except socket.gaierror as exc:
        raise TargetConfigurationError("External target host could not be resolved safely") from exc
    if not addresses:
        raise TargetConfigurationError("External target host did not resolve to an address")
    if not config.ALLOW_PRIVATE_EXTERNAL_TARGETS and any(_is_private_host(address) for address in addresses):
        raise TargetConfigurationError("External target resolved to a private or reserved network address")


def _same_origin(expected: str, actual: str) -> bool:
    expected_url = urlparse(expected)
    actual_url = urlparse(actual)

    def port(value) -> int | None:
        if value.port is not None:
            return value.port
        return 443 if value.scheme == "https" else 80 if value.scheme == "http" else None

    return (
        expected_url.scheme.lower(),
        (expected_url.hostname or "").lower(),
        port(expected_url),
    ) == (
        actual_url.scheme.lower(),
        (actual_url.hostname or "").lower(),
        port(actual_url),
    )


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201, ARG002
        return None


_SECURE_OPENER = urllib.request.build_opener(_RejectRedirects())


def _secure_urlopen(request: urllib.request.Request, *, timeout: float):
    return _SECURE_OPENER.open(request, timeout=timeout)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
