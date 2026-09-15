"""Saved run exports use the immutable manifest retained by the repository."""

import json

import pandas as pd
import pytest

from src import database
from src.chunker import chunk_documents
from src.evaluator import run_evaluation
from src.reporting import build_report_payload
from src.storage import SQLiteRepository


def test_live_run_manifest_and_source_notices_survive_sqlite_report_readback(tmp_path):
    repository = SQLiteRepository(tmp_path / "run.sqlite3")
    context = repository.local_context()
    document = {
        "filename": "partial-policy.pdf",
        "text": "The Basic plan retains records for 30 days.",
        "warnings": ["Page 2 contains no searchable text."],
    }
    repository.save_documents_and_chunks(context, [document], chunk_documents([document]))
    chunks = repository.load_chunks(context)
    dataset = pd.DataFrame(
        [
            {
                "case_id": "retention",
                "question": "How long does Basic retain records?",
                "expected_answer": document["text"],
                "expected_source": chunks[0]["source_name"],
                "category": "routine",
                "should_escalate": False,
            }
        ]
    )
    with database.request_scope(repository, context):
        memory = run_evaluation(
            dataset,
            chunks,
            {"Current": "Use only source evidence."},
            "mock-model",
            1,
            0,
            3500,
            0.03,
            "fixture",
            max_concurrency=1,
        )
    manifest = memory.iloc[0]["manifest"]
    memory_report = build_report_payload(memory)
    reloaded = pd.DataFrame(SQLiteRepository(repository.path).list_results(context, int(memory.iloc[0]["run_id"])))
    restored_report = build_report_payload(reloaded)
    assert reloaded.iloc[0]["manifest"] == manifest
    assert reloaded.iloc[0]["manifest_hash"] == manifest["manifest_hash"]
    assert restored_report["run_manifests"] == memory_report["run_manifests"]
    for field in (
        "document_versions",
        "target_versions",
        "target_types",
        "dataset_versions",
        "evaluator_versions",
        "source_extraction_notices",
    ):
        assert restored_report["metadata"][field] == memory_report["metadata"][field]
    assert restored_report["metadata"]["source_extraction_notices"] == [
        "partial-policy.pdf: Page 2 contains no searchable text."
    ]
    with repository.connection() as conn:
        persisted = json.loads(conn.execute("SELECT manifest_json FROM eval_runs").fetchone()[0])
    assert persisted == manifest


@pytest.mark.parametrize("stored", ["{}", "null", "[]", "malformed"])
def test_historical_missing_run_manifest_stays_unknown(tmp_path, stored):
    repository = SQLiteRepository(tmp_path / "historical.sqlite3")
    context = repository.local_context()
    run_id = repository.create_run(
        context, run_name="Historical", model_name="unknown", mode="batch", unique_case_count=1, total_executions=1
    )
    repository.save_result(
        context, run_id, {"case_id": "old", "question": "Old question", "execution_status": "failed"}
    )
    with repository.connection() as conn:
        conn.execute("UPDATE eval_runs SET manifest_json = ?", (stored,))
    reloaded = repository.latest_results(context)
    assert not reloaded[0].get("manifest")
    assert not reloaded[0].get("manifest_hash")
    assert build_report_payload(pd.DataFrame(reloaded))["run_manifests"] == []
