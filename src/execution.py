from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

from src.domain import ExecutionStatus, TargetResponse
from src.targets import TargetAdapter, TargetConfigurationError
from src.versioning import canonical_json

TERMINAL_STATUSES = {
    ExecutionStatus.PASSED,
    ExecutionStatus.FAILED,
    ExecutionStatus.TIMED_OUT,
    ExecutionStatus.RATE_LIMITED,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.INVALID_RESPONSE,
}
RETRYABLE_STATUSES = {
    ExecutionStatus.FAILED,
    ExecutionStatus.TIMED_OUT,
    ExecutionStatus.RATE_LIMITED,
}


@dataclass(frozen=True)
class ExecutionPolicy:
    max_concurrency: int = 4
    max_retries: int = 2
    backoff_seconds: float = 0.5
    maximum_backoff_seconds: float = 10.0
    cache_enabled: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.max_concurrency <= 64:
            raise ValueError("max_concurrency must be between 1 and 64")
        if not 0 <= self.max_retries <= 10:
            raise ValueError("max_retries must be between 0 and 10")


@dataclass
class ExecutionRecord:
    execution_key: str
    case_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    attempt_count: int = 0
    response: TargetResponse | None = None
    started_at: float | None = None
    completed_at: float | None = None
    cache_hit: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_key": self.execution_key,
            "case_id": self.case_id,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "response": asdict(self.response) if self.response else None,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "cache_hit": self.cache_hit,
            "metadata": self.metadata,
        }


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class ExecutionCache:
    def __init__(self) -> None:
        self._values: dict[str, TargetResponse] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> TargetResponse | None:
        with self._lock:
            return self._values.get(key)

    def set(self, key: str, response: TargetResponse) -> None:
        if response.status == ExecutionStatus.PASSED:
            with self._lock:
                self._values[key] = response


class ExecutionEngine:
    def __init__(
        self,
        target: TargetAdapter,
        policy: ExecutionPolicy | None = None,
        *,
        cache: ExecutionCache | None = None,
        sleep: Callable[[float], None] = time.sleep,
        checkpoint: Callable[[ExecutionRecord], None] | None = None,
    ) -> None:
        self.target = target
        self.policy = policy or ExecutionPolicy()
        self.cache = cache or ExecutionCache()
        self.sleep = sleep
        self.checkpoint = checkpoint
        self._submitted: set[str] = set()
        self._submission_lock = threading.Lock()

    def run(
        self,
        requests: Iterable[dict[str, Any]],
        *,
        cancellation: CancellationToken | None = None,
        progress: Callable[[int, int, ExecutionRecord], None] | None = None,
        completed: dict[str, ExecutionRecord] | None = None,
    ) -> list[ExecutionRecord]:
        cancellation = cancellation or CancellationToken()
        completed = completed or {}
        request_list = list(requests)
        records: list[ExecutionRecord] = []
        pending: list[tuple[dict[str, Any], ExecutionRecord]] = []
        for request in request_list:
            key = execution_cache_key(request, self.target.version)
            existing = completed.get(key)
            if existing and existing.status in TERMINAL_STATUSES:
                records.append(existing)
                continue
            record = ExecutionRecord(execution_key=key, case_id=str(request.get("case_id") or key[:12]))
            records.append(record)
            pending.append((request, record))
        total = len(records)
        done = len(records) - len(pending)
        if progress:
            for record in records[:done]:
                progress(done, total, record)

        with ThreadPoolExecutor(max_workers=self.policy.max_concurrency, thread_name_prefix="ars-exec") as pool:
            futures: dict[Future[ExecutionRecord], ExecutionRecord] = {}
            for request, record in pending:
                if cancellation.cancelled:
                    record.status = ExecutionStatus.CANCELLED
                    record.completed_at = time.time()
                    self._save_checkpoint(record)
                    done += 1
                    if progress:
                        progress(done, total, record)
                    continue
                with self._submission_lock:
                    if record.execution_key in self._submitted:
                        record.status = ExecutionStatus.CANCELLED
                        record.metadata["duplicate_prevented"] = True
                        record.completed_at = time.time()
                        self._save_checkpoint(record)
                        done += 1
                        if progress:
                            progress(done, total, record)
                        continue
                    self._submitted.add(record.execution_key)
                future = pool.submit(self._execute_one, request, record, cancellation)
                futures[future] = record
            for future in as_completed(futures):
                record = future.result()
                done += 1
                if progress:
                    progress(done, total, record)
        return records

    def _execute_one(
        self,
        request: dict[str, Any],
        record: ExecutionRecord,
        cancellation: CancellationToken,
    ) -> ExecutionRecord:
        record.started_at = time.time()
        if cancellation.cancelled:
            record.status = ExecutionStatus.CANCELLED
            record.completed_at = time.time()
            self._save_checkpoint(record)
            return record
        cached = self.cache.get(record.execution_key) if self.policy.cache_enabled else None
        if cached is not None:
            record.status = cached.status
            record.response = cached
            record.cache_hit = True
            record.completed_at = time.time()
            self._save_checkpoint(record)
            return record
        record.status = ExecutionStatus.RUNNING
        self._save_checkpoint(record)
        for attempt in range(self.policy.max_retries + 1):
            if cancellation.cancelled:
                record.status = ExecutionStatus.CANCELLED
                break
            record.attempt_count = attempt + 1
            try:
                response = self.target.execute(request)
            except TargetConfigurationError:
                response = TargetResponse(
                    status=ExecutionStatus.INVALID_RESPONSE,
                    error_code="target_configuration_error",
                    safe_error="The target configuration could not be resolved. Sensitive details were withheld.",
                    metadata={"quality_score_eligible": False},
                )
            except Exception:  # Adapters and third-party clients expose heterogeneous exception types.
                response = TargetResponse(
                    status=ExecutionStatus.FAILED,
                    error_code="target_adapter_error",
                    safe_error="The target adapter failed. Sensitive details were withheld.",
                    metadata={"quality_score_eligible": False},
                )
            record.response = response
            record.status = response.status
            self._save_checkpoint(record)
            if response.status == ExecutionStatus.PASSED:
                self.cache.set(record.execution_key, response)
                break
            if response.status not in RETRYABLE_STATUSES or attempt >= self.policy.max_retries:
                break
            delay = min(self.policy.maximum_backoff_seconds, self.policy.backoff_seconds * (2**attempt))
            self.sleep(delay)
        record.completed_at = time.time()
        self._save_checkpoint(record)
        return record

    def _save_checkpoint(self, record: ExecutionRecord) -> None:
        if self.checkpoint:
            self.checkpoint(record)


def execution_cache_key(request: dict[str, Any], target_version: str) -> str:
    key_material = {
        "target_version": target_version,
        "prompt_version": request.get("prompt_version"),
        "dataset_case": request.get("case_id") or request.get("question"),
        "dataset_version": request.get("dataset_version"),
        "document_versions": request.get("document_versions", []),
        "retrieval_configuration": request.get("retrieval_configuration", {}),
        "evaluation_configuration": request.get("evaluation_configuration", {}),
        "request_variables": request.get("variables", {}),
    }
    return hashlib.sha256(canonical_json(key_material).encode("utf-8")).hexdigest()
