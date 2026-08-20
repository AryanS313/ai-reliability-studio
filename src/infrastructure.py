from __future__ import annotations

import hashlib
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from src.security import sanitize_filename
from src.versioning import version_hash


class InfrastructureCapabilityError(RuntimeError):
    pass


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobRecord:
    job_id: str
    kind: str
    payload: dict[str, Any]
    idempotency_key: str
    state: JobState = JobState.PENDING
    attempts: int = 0
    created_at: float = field(default_factory=time.time)
    available_at: float = field(default_factory=time.time)
    heartbeat_at: float | None = None
    lease_expires_at: float | None = None
    worker_id: str | None = None
    cancel_requested: bool = False
    safe_error_code: str | None = None
    result_reference: str | None = None


class JobQueue(ABC):
    production_ready: bool = False

    @abstractmethod
    def enqueue(self, kind: str, payload: dict[str, Any], *, idempotency_key: str) -> JobRecord:
        raise NotImplementedError

    @abstractmethod
    def claim(self, worker_id: str, *, lease_seconds: float = 60.0, now: float | None = None) -> JobRecord | None:
        raise NotImplementedError

    @abstractmethod
    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
        now: float | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def complete(self, job_id: str, worker_id: str, *, result_reference: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def fail(
        self,
        job_id: str,
        worker_id: str,
        *,
        safe_error_code: str,
        retryable: bool,
        max_attempts: int,
        retry_delay_seconds: float = 0.0,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def request_cancel(self, job_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def recover_stale(self, *, now: float | None = None) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def get(self, job_id: str) -> JobRecord | None:
        raise NotImplementedError


class InMemoryJobQueue(JobQueue):
    """Thread-safe development adapter. State is lost when the process exits."""

    production_ready = False

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = threading.RLock()

    def enqueue(self, kind: str, payload: dict[str, Any], *, idempotency_key: str) -> JobRecord:
        if not kind.strip() or not idempotency_key.strip():
            raise ValueError("Jobs require a kind and idempotency key.")
        with self._lock:
            existing_id = self._idempotency.get(idempotency_key)
            if existing_id:
                return self._copy(self._jobs[existing_id])
            job_id = version_hash({"kind": kind, "idempotency_key": idempotency_key, "created_ns": time.time_ns()})
            record = JobRecord(
                job_id=job_id,
                kind=kind,
                payload=dict(payload),
                idempotency_key=idempotency_key,
            )
            self._jobs[job_id] = record
            self._idempotency[idempotency_key] = job_id
            return self._copy(record)

    def claim(self, worker_id: str, *, lease_seconds: float = 60.0, now: float | None = None) -> JobRecord | None:
        if not worker_id.strip() or lease_seconds <= 0:
            raise ValueError("Claims require a worker ID and positive lease.")
        current = now if now is not None else time.time()
        with self._lock:
            for record in sorted(self._jobs.values(), key=lambda item: (item.available_at, item.created_at)):
                if record.state != JobState.PENDING or record.available_at > current:
                    continue
                if record.cancel_requested:
                    record.state = JobState.CANCELLED
                    continue
                record.state = JobState.RUNNING
                record.worker_id = worker_id
                record.attempts += 1
                record.heartbeat_at = current
                record.lease_expires_at = current + lease_seconds
                return self._copy(record)
        return None

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
        now: float | None = None,
    ) -> None:
        current = now if now is not None else time.time()
        with self._lock:
            record = self._owned_running(job_id, worker_id)
            if record.cancel_requested:
                record.state = JobState.CANCELLED
                record.worker_id = None
                record.lease_expires_at = None
                return
            record.heartbeat_at = current
            record.lease_expires_at = current + lease_seconds

    def complete(self, job_id: str, worker_id: str, *, result_reference: str | None = None) -> None:
        with self._lock:
            record = self._owned_running(job_id, worker_id)
            if record.cancel_requested:
                record.state = JobState.CANCELLED
            else:
                record.state = JobState.SUCCEEDED
                record.result_reference = result_reference
            record.worker_id = None
            record.lease_expires_at = None

    def fail(
        self,
        job_id: str,
        worker_id: str,
        *,
        safe_error_code: str,
        retryable: bool,
        max_attempts: int,
        retry_delay_seconds: float = 0.0,
    ) -> None:
        if not safe_error_code.strip():
            raise ValueError("Failures require a safe error code.")
        with self._lock:
            record = self._owned_running(job_id, worker_id)
            record.safe_error_code = safe_error_code
            if record.cancel_requested:
                record.state = JobState.CANCELLED
            elif retryable and record.attempts < max_attempts:
                record.state = JobState.PENDING
                record.available_at = time.time() + max(0.0, retry_delay_seconds)
            else:
                record.state = JobState.FAILED
            record.worker_id = None
            record.lease_expires_at = None

    def request_cancel(self, job_id: str) -> None:
        with self._lock:
            record = self._require(job_id)
            record.cancel_requested = True
            if record.state == JobState.PENDING:
                record.state = JobState.CANCELLED

    def recover_stale(self, *, now: float | None = None) -> list[str]:
        current = now if now is not None else time.time()
        recovered = []
        with self._lock:
            for record in self._jobs.values():
                if (
                    record.state == JobState.RUNNING
                    and record.lease_expires_at is not None
                    and record.lease_expires_at < current
                ):
                    record.state = JobState.CANCELLED if record.cancel_requested else JobState.PENDING
                    record.worker_id = None
                    record.lease_expires_at = None
                    record.available_at = current
                    recovered.append(record.job_id)
        return sorted(recovered)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return self._copy(record) if record else None

    def _owned_running(self, job_id: str, worker_id: str) -> JobRecord:
        record = self._require(job_id)
        if record.state != JobState.RUNNING or record.worker_id != worker_id:
            raise InfrastructureCapabilityError("The worker does not own an active lease for this job.")
        return record

    def _require(self, job_id: str) -> JobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"Unknown job: {job_id}") from exc

    @staticmethod
    def _copy(record: JobRecord) -> JobRecord:
        return JobRecord(**{**record.__dict__, "payload": dict(record.payload)})


class ArtifactStore(ABC):
    production_ready: bool = False

    @abstractmethod
    def put(self, workspace_id: int, key: str, content: bytes) -> str:
        raise NotImplementedError

    @abstractmethod
    def read(self, workspace_id: int, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def delete(self, workspace_id: int, key: str) -> bool:
        raise NotImplementedError


class LocalArtifactStore(ArtifactStore):
    """Atomic local artifact storage for single-process development only."""

    production_ready = False

    def __init__(self, root: str | Path, *, maximum_bytes: int = 100 * 1024 * 1024) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.maximum_bytes = maximum_bytes

    def put(self, workspace_id: int, key: str, content: bytes) -> str:
        if workspace_id <= 0:
            raise ValueError("workspace_id must be positive.")
        if len(content) > self.maximum_bytes:
            raise ValueError(f"Artifact exceeds the {self.maximum_bytes} byte limit.")
        path = self._path(workspace_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, prefix=".upload-", delete=False) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        return f"artifact://workspace/{workspace_id}/{path.name}"

    def read(self, workspace_id: int, key: str) -> bytes:
        return self._path(workspace_id, key).read_bytes()

    def delete(self, workspace_id: int, key: str) -> bool:
        path = self._path(workspace_id, key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path(self, workspace_id: int, key: str) -> Path:
        safe_name = sanitize_filename(Path(key).name)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        suffix = Path(safe_name).suffix[:20]
        path = (self.root / f"workspace-{workspace_id}" / digest[:2] / f"{digest}{suffix}").resolve()
        if self.root not in path.parents:
            raise ValueError("Artifact path escaped the configured root.")
        return path


class ScanVerdict(str, Enum):
    CLEAN = "clean"
    MALICIOUS = "malicious"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ScanResult:
    verdict: ScanVerdict
    scanner: str
    signature_version: str | None = None
    safe_reason: str | None = None


class MalwareScanner(ABC):
    production_ready: bool = False

    @abstractmethod
    def scan(self, content: bytes, filename: str) -> ScanResult:
        raise NotImplementedError


class UnavailableMalwareScanner(MalwareScanner):
    production_ready = False

    def scan(self, content: bytes, filename: str) -> ScanResult:
        return ScanResult(
            verdict=ScanVerdict.UNAVAILABLE,
            scanner="unavailable-local-adapter",
            safe_reason="No malware scanner is configured; production ingestion must fail closed or quarantine the file.",
        )


@dataclass(frozen=True)
class OCRResult:
    available: bool
    text: str = ""
    provider: str = "unavailable"
    safe_warning: str | None = None


class OCRPipeline(ABC):
    production_ready: bool = False

    @abstractmethod
    def extract(self, content: bytes, *, filename: str, language: str | None = None) -> OCRResult:
        raise NotImplementedError


class UnavailableOCRPipeline(OCRPipeline):
    production_ready = False

    def extract(self, content: bytes, *, filename: str, language: str | None = None) -> OCRResult:
        return OCRResult(
            available=False,
            safe_warning="OCR is not configured. Scanned content was not treated as successfully extracted.",
        )


@dataclass(frozen=True)
class RetentionPolicy:
    retention_days: int
    legal_hold: bool = False
    delete_artifacts: bool = True

    def __post_init__(self) -> None:
        if self.retention_days < 0:
            raise ValueError("retention_days cannot be negative.")

    @property
    def version(self) -> str:
        return version_hash(self.__dict__)

    def cutoff(self, *, now: datetime | None = None) -> datetime | None:
        if self.legal_hold:
            return None
        current = now or datetime.now(UTC)
        return current - timedelta(days=self.retention_days)


@dataclass(frozen=True)
class ScheduleRegistration:
    schedule_id: str
    expression: str
    timezone: str
    job_kind: str
    payload: dict[str, Any]
    enabled: bool


class ScheduleRegistry(ABC):
    production_ready: bool = False

    @abstractmethod
    def register(
        self,
        expression: str,
        timezone_name: str,
        job_kind: str,
        payload: dict[str, Any],
        *,
        enabled: bool,
    ) -> ScheduleRegistration:
        raise NotImplementedError


class LocalScheduleRegistry(ScheduleRegistry):
    """Configuration registry only; it does not execute jobs or survive restarts."""

    production_ready = False

    def __init__(self) -> None:
        self._items: dict[str, ScheduleRegistration] = {}

    def register(
        self,
        expression: str,
        timezone_name: str,
        job_kind: str,
        payload: dict[str, Any],
        *,
        enabled: bool,
    ) -> ScheduleRegistration:
        if enabled and (not expression.strip() or not job_kind.strip()):
            raise ValueError("Enabled schedules require an expression and job kind.")
        schedule_id = version_hash(
            {
                "expression": expression,
                "timezone": timezone_name,
                "job_kind": job_kind,
                "payload": payload,
            }
        )
        registration = ScheduleRegistration(
            schedule_id=schedule_id,
            expression=expression,
            timezone=timezone_name,
            job_kind=job_kind,
            payload=dict(payload),
            enabled=enabled,
        )
        self._items[schedule_id] = registration
        return registration
