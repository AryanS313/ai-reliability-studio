from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.security import redact_pii, redact_secrets


class NotificationHook(ABC):
    @abstractmethod
    def send(self, event: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError


class NoOpNotificationHook(NotificationHook):
    def send(self, event: str, payload: dict[str, Any]) -> None:
        return None


@dataclass(frozen=True)
class ScheduleDefinition:
    expression: str
    timezone: str = "UTC"
    enabled: bool = False

    def __post_init__(self) -> None:
        if self.enabled and not self.expression.strip():
            raise ValueError("Enabled schedules require an expression.")


def ingest_production_logs(
    records: Iterable[dict[str, Any]],
    *,
    redact_personal_data: bool = True,
    maximum_records: int = 10000,
) -> list[dict[str, Any]]:
    output = []
    for index, record in enumerate(records):
        if index >= maximum_records:
            raise ValueError(f"Production log batch exceeds the {maximum_records} record limit.")
        safe = redact_secrets(record, preserve_references=False)
        if redact_personal_data:
            safe = _redact_nested(safe)
        safe["ingested_at"] = datetime.now(UTC).isoformat()
        output.append(safe)
    return output


def quality_drift(baseline: list[float], current: list[float]) -> dict[str, Any]:
    if not baseline or not current:
        return {"available": False, "reason": "Both baseline and current samples are required."}
    baseline_mean = sum(baseline) / len(baseline)
    current_mean = sum(current) / len(current)
    delta = current_mean - baseline_mean
    return {
        "available": True,
        "baseline_mean": baseline_mean,
        "current_mean": current_mean,
        "delta": delta,
        "regression": delta < -0.02,
    }


def _redact_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_nested(item) for item in value]
    return redact_pii(value) if isinstance(value, str) else value
