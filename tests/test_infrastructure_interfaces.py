from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from src.infrastructure import (
    InfrastructureCapabilityError,
    InMemoryJobQueue,
    JobState,
    LocalArtifactStore,
    LocalScheduleRegistry,
    RetentionPolicy,
    ScanVerdict,
    UnavailableMalwareScanner,
    UnavailableOCRPipeline,
)


def test_in_memory_queue_idempotency_leases_retries_heartbeats_and_recovery():
    queue = InMemoryJobQueue()
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(
            pool.map(
                lambda _: queue.enqueue("evaluation", {"run_id": 7}, idempotency_key="workspace-1-run-7"),
                range(20),
            )
        )
    assert len({record.job_id for record in records}) == 1
    assert queue.production_ready is False

    started = time.time()
    claimed = queue.claim("worker-a", lease_seconds=10, now=started)
    assert claimed is not None
    assert claimed.state == JobState.RUNNING
    assert claimed.attempts == 1
    queue.heartbeat(claimed.job_id, "worker-a", lease_seconds=10, now=started + 5)
    assert queue.recover_stale(now=started + 10) == []
    assert queue.recover_stale(now=started + 16) == [claimed.job_id]

    retried = queue.claim("worker-b", now=started + 16)
    assert retried is not None and retried.attempts == 2
    queue.fail(
        retried.job_id,
        "worker-b",
        safe_error_code="provider_rate_limit",
        retryable=True,
        max_attempts=3,
    )
    final_attempt = queue.claim("worker-c")
    assert final_attempt is not None and final_attempt.attempts == 3
    queue.complete(final_attempt.job_id, "worker-c", result_reference="artifact://result")
    finished = queue.get(final_attempt.job_id)
    assert finished is not None and finished.state == JobState.SUCCEEDED
    assert finished.result_reference == "artifact://result"
    with pytest.raises(InfrastructureCapabilityError):
        queue.complete(final_attempt.job_id, "worker-c")


def test_queue_cancellation_is_cooperative_and_stale_cancel_is_terminal():
    queue = InMemoryJobQueue()
    pending = queue.enqueue("evaluation", {}, idempotency_key="pending")
    queue.request_cancel(pending.job_id)
    assert queue.get(pending.job_id).state == JobState.CANCELLED  # type: ignore[union-attr]

    running = queue.enqueue("evaluation", {}, idempotency_key="running")
    started = time.time()
    claim = queue.claim("worker", lease_seconds=1, now=started)
    assert claim is not None and claim.job_id == running.job_id
    queue.request_cancel(running.job_id)
    queue.heartbeat(running.job_id, "worker", now=started + 0.5)
    assert queue.get(running.job_id).state == JobState.CANCELLED  # type: ignore[union-attr]


def test_local_artifacts_are_atomic_workspace_scoped_and_size_limited(tmp_path):
    store = LocalArtifactStore(tmp_path / "artifacts", maximum_bytes=8)
    reference = store.put(1, "../../report.json", b"evidence")
    assert reference.startswith("artifact://workspace/1/")
    assert store.read(1, "../../report.json") == b"evidence"
    with pytest.raises(FileNotFoundError):
        store.read(2, "../../report.json")
    with pytest.raises(ValueError, match="byte limit"):
        store.put(1, "large.bin", b"012345678")
    assert store.delete(1, "../../report.json") is True
    assert store.delete(1, "../../report.json") is False
    assert store.production_ready is False


def test_unavailable_security_and_ocr_adapters_never_claim_success():
    scan = UnavailableMalwareScanner().scan(b"content", "scan.pdf")
    assert scan.verdict == ScanVerdict.UNAVAILABLE
    assert "must fail closed or quarantine" in str(scan.safe_reason)
    ocr = UnavailableOCRPipeline().extract(b"image", filename="scan.pdf")
    assert ocr.available is False
    assert "not configured" in str(ocr.safe_warning)


def test_retention_legal_hold_and_local_schedule_limitations():
    now = datetime(2026, 8, 20, tzinfo=UTC)
    policy = RetentionPolicy(30)
    assert policy.cutoff(now=now).date().isoformat() == "2026-07-21"  # type: ignore[union-attr]
    assert RetentionPolicy(30, legal_hold=True).cutoff(now=now) is None
    with pytest.raises(ValueError):
        RetentionPolicy(-1)

    registry = LocalScheduleRegistry()
    schedule = registry.register("0 2 * * *", "UTC", "evaluation", {"project_id": 1}, enabled=True)
    assert schedule.enabled is True
    assert registry.production_ready is False
    with pytest.raises(ValueError):
        registry.register("", "UTC", "", {}, enabled=True)
