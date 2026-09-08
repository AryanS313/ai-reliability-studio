"""Opt-in sequential execution for the pinned Stlite/Emscripten runtime.

This changes scheduling only. The upstream per-request execution/retry/cache
method is inherited unchanged. Install before importing the application entry.
"""

from __future__ import annotations

import hashlib
import sys
import time
from itertools import islice
from pathlib import Path
from typing import Any

from src import config
from src import execution as _execution
from src.domain import ExecutionStatus

EXECUTION_SOURCE_SHA256 = "400068675b24cdd84706df0d6a6b8a1491fee82b33916d994b5e314443a9d5d2"
RUNTIME_VERSION = "browser-sequential-v1"
_NativeEngine = _execution.ExecutionEngine


class BrowserRunLimitError(ValueError):
    """A batch exceeded the explicit browser case limit before any target call."""


class NativeThreadsUnavailable(RuntimeError):
    """The browser execution module must never construct a native thread pool."""


class BrowserRunAborted(RuntimeError):
    """Infrastructure/callback failure; retained records are not claimed saved."""

    def __init__(self, records: tuple[_execution.ExecutionRecord, ...]) -> None:
        self.records = records
        self.completed_records = tuple(
            record
            for record in records
            if record.status in _execution.TERMINAL_STATUSES and record.completed_at is not None
        )
        super().__init__(
            "The browser run stopped after an execution or reporting problem. "
            "Completed records are available on this error for recovery; they are not guaranteed saved. "
            "Remaining records were not completed. Sensitive details were withheld."
        )


class _ForbiddenThreadPool:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NativeThreadsUnavailable(
            "Native execution threads are unavailable in this browser runtime. "
            "Use BrowserSequentialExecutionEngine with max_concurrency=1."
        )


class BrowserSequentialExecutionEngine(_NativeEngine):
    """Run each request to completion before starting the next request.

    Cancellation is checked by the inherited per-request method and between
    requests. This synchronous API does not create a responsive browser Stop
    button or abort an in-flight provider call.
    """

    def __init__(self, target, policy=None, *, case_limit=None, **kwargs) -> None:
        if sys.platform != "emscripten":
            raise RuntimeError("This execution adapter is only for Emscripten.")
        policy = policy or _execution.ExecutionPolicy(max_concurrency=1, max_retries=target.default_retry_count)
        if policy.max_concurrency != 1:
            raise ValueError("Browser execution requires max_concurrency=1; it runs one question at a time.")
        self.case_limit = config.MAX_DATASET_ROWS if case_limit is None else case_limit
        if isinstance(self.case_limit, bool) or not isinstance(self.case_limit, int) or self.case_limit < 1:
            raise ValueError("The browser case limit must be a positive integer.")
        self.last_records: tuple[_execution.ExecutionRecord, ...] = ()
        super().__init__(target, policy, **kwargs)

    def run(self, requests, *, cancellation=None, progress=None, completed=None):
        self.last_records = ()
        # Bound arbitrary iterables and reject oversize batches without truncating.
        request_list = list(islice(iter(requests), self.case_limit + 1))
        if len(request_list) > self.case_limit:
            raise BrowserRunLimitError(
                f"This browser run exceeds the {self.case_limit}-case limit. Split it into smaller batches."
            )
        if any(not isinstance(request, dict) for request in request_list):
            raise ValueError("Every execution request must be an object.")
        cancellation = cancellation or _execution.CancellationToken()
        completed = completed or {}
        records = []
        pending = []
        reused = []
        for request in request_list:
            key = _execution.execution_cache_key(request, self.target.version)
            existing = completed.get(key)
            if existing and existing.status in _execution.TERMINAL_STATUSES:
                records.append(existing)
                reused.append(existing)
                continue
            record = _execution.ExecutionRecord(
                execution_key=key,
                case_id=str(request.get("case_id") or key[:12]),
                metadata={"execution_runtime": RUNTIME_VERSION, "effective_concurrency": 1},
            )
            records.append(record)
            pending.append((request, record))
        self.last_records = tuple(records)
        done, total = 0, len(records)
        try:
            # Reused records may be interleaved with pending records in the input.
            for record in reused:
                done += 1
                if progress:
                    progress(done, total, record)
            for request, record in pending:
                if cancellation.cancelled:
                    record.status = ExecutionStatus.CANCELLED
                    record.completed_at = time.time()
                    self._save_checkpoint(record)
                elif record.execution_key in self._submitted:
                    record.status = ExecutionStatus.CANCELLED
                    record.metadata["duplicate_prevented"] = True
                    record.completed_at = time.time()
                    self._save_checkpoint(record)
                else:
                    self._submitted.add(record.execution_key)
                    self._execute_one(request, record, cancellation)
                done += 1
                if progress:
                    progress(done, total, record)
        except Exception:
            # Keep audit/checkpoint failures fatal instead of calling them target
            # failures or claiming unsaved records were persisted successfully.
            raise BrowserRunAborted(self.last_records) from None
        return records


def install_browser_execution() -> dict[str, Any]:
    """Install only on Emscripten and only against the reviewed execution source."""
    if sys.platform != "emscripten":
        return {"installed": False, "reason": "native_runtime_unchanged"}
    source_hash = hashlib.sha256(Path(_execution.__file__).read_bytes()).hexdigest()
    if source_hash != EXECUTION_SOURCE_SHA256:
        raise RuntimeError("The execution module changed. Review this browser adapter before enabling it.")
    _execution.ThreadPoolExecutor = _ForbiddenThreadPool
    _execution.ExecutionEngine = BrowserSequentialExecutionEngine
    evaluator = sys.modules.get("src.evaluator")
    if evaluator is not None:
        evaluator.ExecutionEngine = BrowserSequentialExecutionEngine
    return {
        "installed": True,
        "runtime_version": RUNTIME_VERSION,
        "effective_concurrency": 1,
        "native_execution_threads": False,
        "source_sha256": source_hash,
    }
