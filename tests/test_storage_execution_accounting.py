from __future__ import annotations

import json
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pandas as pd
import pytest

from src.domain import Role, WorkspaceContext
from src.presentation import retry_summary
from src.storage import PostgresRepository, SQLiteRepository


def _result(**values):
    return {
        "case_id": "case-1",
        "question": "Fictional storage check",
        "execution_status": "failed",
        "prompt_version": "prompt-v1",
        "target_version": "target-v1",
        **values,
    }


def _sqlite_run(tmp_path):
    repository = SQLiteRepository(tmp_path / "accounting.sqlite3")
    context = repository.create_workspace("accounting@example.test", "Accounting")
    run_id = repository.create_run(
        context,
        run_name="Accounting check",
        model_name="unknown",
        mode="batch",
        unique_case_count=1,
        total_executions=1,
    )
    return repository, context, run_id


@pytest.mark.parametrize(("attempts", "cache_hit"), [(3, False), (0, True), (1, False)])
@pytest.mark.parametrize("metadata_format", ["top_level", "metadata", "metadata_json"])
def test_sqlite_roundtrip_retains_real_execution_observations(tmp_path, attempts, cache_hit, metadata_format):
    repository, context, run_id = _sqlite_run(tmp_path)
    accounting = {"attempt_count": attempts, "cache_hit": cache_hit, "execution_key": "engine-key"}
    identity = {"provenance": "not_reported", "reported_model": None}
    metadata = {"model_identity": identity}
    if metadata_format == "top_level":
        result = _result(**accounting, metadata=metadata)
    else:
        metadata["execution"] = {**accounting, "max_retries": 3}
        result = _result(**{metadata_format: json.dumps(metadata) if metadata_format == "metadata_json" else metadata})
    original = deepcopy(result)
    repository.save_result(context, run_id, result)
    assert result == original

    restored = repository.latest_results(context)[0]
    assert {key: restored[key] for key in accounting} == accounting
    assert restored["metadata"]["model_identity"] == identity
    assert json.loads(restored["metadata_json"])["execution"].items() >= accounting.items()
    assert retry_summary(pd.DataFrame([restored]))["retries"] == max(attempts - 1, 0)
    with repository.connection() as conn:
        stored = conn.execute("SELECT attempt_count, execution_key, metadata_json FROM executions").fetchone()
    assert stored["attempt_count"] == attempts
    assert stored["execution_key"] != accounting["execution_key"]
    assert json.loads(stored["metadata_json"])["execution"].items() >= accounting.items()


@pytest.mark.parametrize("metadata", [{}, {"execution": {}}, {"execution": {"attempt_count": True}}, "broken-json"])
def test_sqlite_historical_missing_or_invalid_accounting_stays_unknown(tmp_path, metadata):
    repository, context, run_id = _sqlite_run(tmp_path)
    repository.save_result(context, run_id, _result())
    # Reproduce an old row: raw attempt_count was always 1, with no engine metadata.
    with repository.connection() as conn:
        conn.execute("UPDATE executions SET attempt_count = 1")
        conn.execute(
            "UPDATE eval_results SET metadata_json = ?",
            (metadata if isinstance(metadata, str) else json.dumps(metadata),),
        )
    restored = repository.list_results(context, run_id)[0]
    assert restored["attempt_count"] is None
    assert restored["cache_hit"] is None
    assert restored["execution_key"] is None
    assert retry_summary(pd.DataFrame([restored])) == {
        "retries": None,
        "observed_retries": 0,
        "attempt_counts_recorded": 0,
        "attempt_counts_unknown": 1,
    }


def test_same_engine_key_in_distinct_runs_keeps_separate_storage_records(tmp_path):
    repository, context, first_run = _sqlite_run(tmp_path)
    second_run = repository.create_run(
        context, run_name="Cached run", model_name="unknown", mode="batch", unique_case_count=1, total_executions=1
    )
    repository.save_result(context, first_run, _result(attempt_count=2, cache_hit=False, execution_key="same-key"))
    repository.save_result(context, second_run, _result(attempt_count=0, cache_hit=True, execution_key="same-key"))
    with repository.connection() as conn:
        rows = conn.execute("SELECT execution_key, attempt_count FROM executions ORDER BY run_id").fetchall()
    assert len({row["execution_key"] for row in rows}) == 2
    assert [row["attempt_count"] for row in rows] == [2, 0]


class _PostgresConnection:
    """Capture PostgreSQL statements without opening a database or socket."""

    def __init__(self):
        self.calls = []
        self.result = None

    def execute(self, sql, parameters):
        self.calls.append((sql, parameters))
        if "INSERT INTO eval_results" in sql:
            self.result = json.loads(parameters[-1])
        if "SELECT er.result_json" in sql:
            return SimpleNamespace(
                fetchall=lambda: [
                    {
                        "result_json": self.result,
                        "run_name": "Stored",
                        "timestamp": "2026-09-08",
                        "mode": "batch",
                        "run_status": "completed",
                    }
                ]
            )
        return SimpleNamespace(fetchone=lambda: {"id": 1})


def _mock_postgres(monkeypatch):
    repository = PostgresRepository("postgresql://unused.invalid/unused")
    connection = _PostgresConnection()

    @contextmanager
    def connect():
        yield connection

    monkeypatch.setattr(repository, "connection", connect)
    monkeypatch.setattr(repository, "authorize", lambda *args: Role.OWNER)
    monkeypatch.setattr(repository, "_require_run", lambda *args: None)
    monkeypatch.setattr(repository, "_scope", lambda *args: None)
    return repository, connection, WorkspaceContext(1, 1, Role.OWNER)


@pytest.mark.parametrize(("attempts", "cache_hit"), [(3, False), (0, True)])
def test_postgres_statement_and_readback_use_real_attempt_count(monkeypatch, attempts, cache_hit):
    repository, connection, context = _mock_postgres(monkeypatch)
    accounting = {"attempt_count": attempts, "cache_hit": cache_hit, "execution_key": "engine-key"}
    repository.save_result(context, 1, _result(metadata={"execution": accounting}))
    sql, parameters = next(call for call in connection.calls if "INSERT INTO executions" in call[0])
    assert sql.count("%s") == len(parameters)
    assert parameters[5] == attempts
    assert json.loads(parameters[-1])["execution"] == accounting
    restored = repository.list_results(context, 1)[0]
    assert {key: restored[key] for key in accounting} == accounting


def test_postgres_historical_missing_metadata_does_not_invent_attempts(monkeypatch):
    repository, connection, context = _mock_postgres(monkeypatch)
    connection.result = _result()
    restored = repository.list_results(context, 1)[0]
    assert restored["attempt_count"] is None
    assert restored["cache_hit"] is None
    assert restored["execution_key"] is None
