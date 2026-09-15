"""Reloaded reference passages must retain stored extraction limitations."""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from src.chunker import chunk_documents
from src.document_loader import source_extraction_warnings
from src.domain import Role, WorkspaceContext
from src.storage import PostgresRepository, SQLiteRepository


def test_sqlite_chunk_reload_retains_document_notices_after_project_switch(tmp_path):
    repository = SQLiteRepository(tmp_path / "sources.sqlite3")
    context = repository.create_workspace("sources@example.test", "Sources")
    project = repository.create_project(context, {"name": "Partially extracted policy"})
    document = {
        "filename": "policy.pdf",
        "text": "Basic plan retains records for 30 days.",
        "warnings": ["Page 2 contains no searchable text."],
    }
    chunks = chunk_documents([document])
    repository.save_documents_and_chunks(context, [document], chunks, project)
    reloaded = SQLiteRepository(repository.path).load_chunks(context, project)
    assert source_extraction_warnings(reloaded) == ["policy.pdf: Page 2 contains no searchable text."]
    assert all(chunk["partially_extracted"] is True for chunk in reloaded)
    assert all("document_extraction_warnings" not in chunk for chunk in reloaded)
    assert [chunk["chunk_text"] for chunk in reloaded] == [chunk["chunk_text"] for chunk in chunks]
    assert [chunk["content_hash"] for chunk in reloaded] == [chunk["content_hash"] for chunk in chunks]


@pytest.mark.parametrize("stored", ["[]", "null", "{}", "not json", '[null, 7, ""]'])
def test_sqlite_legacy_empty_or_malformed_notice_metadata_does_not_fabricate_warning(tmp_path, stored):
    repository = SQLiteRepository(tmp_path / "legacy.sqlite3")
    context = repository.create_workspace("legacy@example.test", "Legacy")
    document = {"filename": "policy.txt", "text": "Policy text", "warnings": []}
    repository.save_documents_and_chunks(context, [document], chunk_documents([document]))
    with repository.connection() as conn:
        conn.execute("UPDATE document_versions SET extraction_warnings = ?", (stored,))
    reloaded = repository.load_chunks(context)
    assert source_extraction_warnings(reloaded) == []
    assert "partially_extracted" not in reloaded[0]


@pytest.mark.parametrize("as_json", [False, True])
def test_postgres_chunk_readback_hydrates_native_or_serialized_json_notices(monkeypatch, as_json):
    repository = PostgresRepository("postgresql://unused.invalid/unused")
    notices = ["Page 3 contains no searchable text."]
    captured = []

    def execute(sql, parameters):
        captured.append(sql)
        return SimpleNamespace(
            fetchall=lambda: [
                {
                    "filename": "source.pdf",
                    "chunk_text": "Fictional policy passage",
                    "document_extraction_warnings": json.dumps(notices) if as_json else notices,
                }
            ]
        )

    @contextmanager
    def connection():
        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(repository, "connection", connection)
    monkeypatch.setattr(repository, "authorize", lambda *args: Role.OWNER)
    monkeypatch.setattr(repository, "_require_project", lambda *args, **kwargs: None)
    monkeypatch.setattr(repository, "_scope", lambda *args: None)
    chunks = repository.load_chunks(WorkspaceContext(1, 1, Role.OWNER))
    assert "dv.extraction_warnings AS document_extraction_warnings" in captured[0]
    assert source_extraction_warnings(chunks) == ["source.pdf: Page 3 contains no searchable text."]
    assert chunks[0]["partially_extracted"] is True
