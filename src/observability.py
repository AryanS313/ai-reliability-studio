from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src import config
from src.security import redact_pii, redact_secrets
from src.versioning import APPLICATION_VERSION


@dataclass(frozen=True)
class ObservabilityPolicy:
    """Sink-neutral retention and payload policy.

    The application can enforce payload minimization before emission. The
    deployment's log/trace backend remains responsible for deleting records at
    the returned cutoff.
    """

    retention_days: int = config.LOG_RETENTION_DAYS
    max_message_characters: int = 2000
    include_full_payloads: bool = False

    def __post_init__(self) -> None:
        if self.retention_days < 0 or self.max_message_characters <= 0:
            raise ValueError("Observability retention and message limits must be non-negative and non-zero.")

    def cutoff(self, *, now: datetime | None = None) -> datetime:
        return (now or datetime.now(UTC)) - timedelta(days=self.retention_days)


class JsonFormatter(logging.Formatter):
    def __init__(self, *, policy: ObservabilityPolicy | None = None) -> None:
        super().__init__()
        self.policy = policy or ObservabilityPolicy()

    def format(self, record: logging.LogRecord) -> str:
        try:
            message = _sanitize_observability(record.getMessage())
            payload = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "message": message[: self.policy.max_message_characters],
            }
            fields = getattr(record, "structured_fields", {})
            safe_fields = _sanitize_observability(fields)
            if isinstance(safe_fields, dict):
                payload.update(safe_fields)
            payload["error_category"] = _error_category(payload)
            return json.dumps(payload, default=str)
        except Exception:
            return json.dumps(
                {
                    "timestamp": self.formatTime(record, self.datefmt),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": "Log event could not be sanitized; content was withheld.",
                    "error_category": "observability_error",
                }
            )


def configure_logging(level: int = logging.INFO, *, policy: ObservabilityPolicy | None = None) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(policy=policy))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._gauges: dict[str, float] = {}
        self._lock = threading.Lock()

    def increment(self, metric: str, value: int = 1) -> None:
        with self._lock:
            self._counters[metric] += value

    def gauge(self, metric: str, value: float) -> None:
        with self._lock:
            self._gauges[metric] = value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"counters": dict(self._counters), "gauges": dict(self._gauges)}

    @contextmanager
    def duration(self, metric: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.gauge(metric, (time.perf_counter() - started) * 1000)


def health_check(repository=None) -> dict[str, Any]:
    result = {"status": "healthy", "application_version": APPLICATION_VERSION, "database": "not_checked"}
    if repository is not None:
        try:
            repository.migrate()
            result["database"] = "healthy"
        except Exception:
            result.update({"status": "unhealthy", "database": "unavailable"})
    return result


def _sanitize_observability(value: Any) -> Any:
    redacted = redact_secrets(value, preserve_references=False)
    if isinstance(redacted, dict):
        return {str(key): _sanitize_observability(item) for key, item in redacted.items()}
    if isinstance(redacted, list):
        return [_sanitize_observability(item) for item in redacted]
    if isinstance(redacted, tuple):
        return tuple(_sanitize_observability(item) for item in redacted)
    return redact_pii(redacted) if isinstance(redacted, str) else redacted


def _error_category(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("error_category") or "").strip().lower()
    if explicit in {"user_error", "evaluator_error", "provider_error", "internal_error", "security_event"}:
        return explicit
    code = str(payload.get("error_code") or "").lower()
    if code.startswith(("provider_", "external_", "rate_limit", "target_")):
        return "provider_error"
    if code.startswith(("evaluator_", "judge_", "calibration_")):
        return "evaluator_error"
    if code.startswith(("validation_", "invalid_", "upload_")):
        return "user_error"
    return "internal_error" if payload.get("level") in {"ERROR", "CRITICAL"} else "none"
