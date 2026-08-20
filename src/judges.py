from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from src.domain import ExecutionStatus
from src.targets import SecretResolver, TargetConfigurationError
from src.versioning import text_hash, version_hash

DEFAULT_JUDGE_PROMPT = """Evaluate the candidate answer against the expected behavior and retrieved evidence.
Return JSON only with keys: score (0 to 1), label, rationale, confidence (0 to 1).

Question:
{question}

Expected behavior:
{expected_answer}

Candidate answer:
{actual_answer}

Retrieved evidence (JSON):
{evidence}
"""


@dataclass(frozen=True)
class JudgeConfiguration:
    provider: str
    model: str
    api_key_reference: str
    prompt_template: str = DEFAULT_JUDGE_PROMPT
    temperature: float = 0.0
    seed: int | None = None
    max_tokens: int = 600

    def __post_init__(self) -> None:
        if self.model == "mock-model":
            raise TargetConfigurationError("Synthetic models cannot serve as model-quality judges.")
        if not 0 <= self.temperature <= 2:
            raise TargetConfigurationError("Judge temperature must be between 0 and 2.")
        required = {"question", "expected_answer", "actual_answer", "evidence"}
        fields = set(re.findall(r"\{([a-z_]+)\}", self.prompt_template))
        if not required.issubset(fields):
            raise TargetConfigurationError(f"Judge prompt is missing placeholders: {sorted(required - fields)}")

    @property
    def version(self) -> str:
        return version_hash(asdict(self))


class LLMJudge:
    """Configurable advisory judge with versioned, persisted provenance.

    Deterministic scoring remains authoritative. This service only produces an
    advisory assessment consumed by `score_result` explanations and review queues.
    """

    def __init__(
        self,
        configuration: JudgeConfiguration,
        secrets: SecretResolver | None = None,
        generator: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.configuration = configuration
        self.secrets = secrets or SecretResolver()
        self._generator = generator

    def evaluate(
        self,
        *,
        question: str,
        expected_answer: str,
        actual_answer: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        prompt = self.configuration.prompt_template.format(
            question=question,
            expected_answer=expected_answer,
            actual_answer=actual_answer,
            evidence=json.dumps(retrieved_chunks, ensure_ascii=False, default=str),
        )
        provenance = {
            "provider": self.configuration.provider,
            "model": self.configuration.model,
            "prompt_template": self.configuration.prompt_template,
            "prompt_hash": text_hash(self.configuration.prompt_template),
            "configuration_version": self.configuration.version,
            "temperature": self.configuration.temperature,
            "seed": self.configuration.seed,
            "max_tokens": self.configuration.max_tokens,
        }
        try:
            api_key = self.secrets.resolve(self.configuration.api_key_reference)
            if self._generator is None:
                from src.llm_client import generate_answer

                generator = generate_answer
            else:
                generator = self._generator
            response = generator(
                question=prompt,
                context="",
                system_prompt="Return a strict JSON evaluation. Do not add Markdown.",
                model_name=self.configuration.model,
                api_key=api_key,
                temperature=self.configuration.temperature,
                seed=self.configuration.seed,
                max_tokens=self.configuration.max_tokens,
            )
        except Exception:
            return _unable("judge_configuration_error", provenance)
        if response.get("status") != ExecutionStatus.PASSED.value:
            return _unable(str(response.get("error_code") or "judge_execution_error"), provenance)
        parsed = _parse_judge_json(str(response.get("answer") or ""))
        if parsed is None:
            return _unable("judge_invalid_response", provenance)
        score = _unit_float(parsed.get("score"))
        confidence = _unit_float(parsed.get("confidence"))
        if score is None or confidence is None:
            return _unable("judge_invalid_score", provenance)
        return {
            "status": "passed",
            "score": score,
            "label": str(parsed.get("label") or "advisory"),
            "rationale": str(parsed.get("rationale") or ""),
            "confidence": confidence,
            "configuration": provenance,
            "policy": "advisory_only",
        }


def _parse_judge_json(value: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.I)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _unit_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 4) if 0 <= number <= 1 else None


def _unable(code: str, provenance: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "unable_to_determine",
        "error_code": code,
        "score": None,
        "confidence": 0.0,
        "configuration": provenance,
        "policy": "advisory_only",
    }
