from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from src import config, database
from src.auth import AuthenticationError
from src.domain import Role, WorkspaceContext
from src.security import AuthorizationError
from src.storage import EphemeralSQLiteRepository, SQLiteRepository


def test_public_sessions_never_open_persistent_storage_and_keep_their_own_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "public-demo")
    persisted = tmp_path / "never-opened.sqlite3"
    monkeypatch.setattr(config, "DATABASE_PATH", persisted)
    first_state, second_state = {}, {}
    first = database.initialize_session(first_state)
    repository = database.get_repository()
    assert isinstance(repository, EphemeralSQLiteRepository)
    project = database.save_project({"name": "Private first project"})
    database.save_documents_and_chunks([{"filename": "private.md", "text": "first-only"}], [], project)
    second = database.initialize_session(second_state)
    assert database.get_repository() is not repository
    assert database.get_repository().list_projects(second) == []
    assert database.documents_df().empty
    database.reset_current_workspace(confirm=True)
    database.initialize_session(first_state)
    assert database.get_repository().list_projects(first)[0]["id"] == project
    assert not persisted.exists()
    database.set_repository(None)


def test_interleaved_sessions_do_not_share_contexts(monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "public-demo")
    barrier = Barrier(2)

    def visitor(name):
        state = {}
        context = database.initialize_session(state)
        database.save_project({"name": name})
        barrier.wait()
        return [project["name"] for project in database.get_repository().list_projects(context)]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(visitor, name) for name in ("first", "second")]
        assert [future.result() for future in futures] == [["first"], ["second"]]


def test_failed_authentication_clears_previous_request_context(tmp_path, monkeypatch):
    repository = SQLiteRepository(tmp_path / "auth.sqlite3")
    database.set_repository(repository)
    repository.local_context()
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    database.current_context({})
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    monkeypatch.setenv("AUTH_TRUSTED_PROXY", "true")
    with pytest.raises(AuthenticationError):
        database.current_context({})
    with pytest.raises(AuthenticationError):
        database.current_context()
    database.set_repository(None)


def test_invalid_access_modes_and_unauthenticated_shared_access_fail_closed(monkeypatch):
    for mode in ("typo", "authenticated"):
        monkeypatch.setattr(config, "APP_ACCESS_MODE", mode)
        monkeypatch.setattr(config, "AUTH_MODE", "single-user")
        with pytest.raises(AuthenticationError):
            database.initialize_session({})
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "local")
    monkeypatch.setattr(config, "APP_ENV", "production")
    with pytest.raises(AuthenticationError):
        database.initialize_session({})


def test_disabled_users_and_forged_owner_role_cannot_authorize(tmp_path):
    repository = SQLiteRepository(tmp_path / "roles.sqlite3")
    owner = repository.create_workspace("owner@example.com", "Workspace")
    administrator = repository.add_member(owner, "admin@example.com", Role.ADMIN)
    forged_owner = WorkspaceContext(administrator, owner.workspace_id, Role.OWNER)
    with pytest.raises(AuthorizationError, match="Only owners"):
        repository.add_member(forged_owner, "new@example.com", Role.OWNER)
    with pytest.raises(AuthorizationError, match="Only owners"):
        repository.add_member(forged_owner, "owner@example.com", Role.EDITOR)
    with repository.connection() as conn:
        conn.execute("UPDATE users SET disabled_at = '2026-09-16' WHERE id = ?", (owner.user_id,))
    with pytest.raises(AuthorizationError):
        repository.list_projects(owner)


def test_project_restore_uses_latest_version_and_never_another_project_or_workspace(tmp_path):
    repository = SQLiteRepository(tmp_path / "restore.sqlite3")
    context = repository.create_workspace("owner@example.com", "Workspace")
    first = repository.create_project(context, {"name": "First"})
    second = repository.create_project(context, {"name": "Second"})
    repository.create_dataset_version(context, first, "Cases", [{"case_id": "old"}])
    repository.create_dataset_version(context, first, "Cases", [{"case_id": "current"}])
    repository.create_dataset_version(context, second, "Cases", [{"case_id": "foreign"}])
    repository.create_target_version(context, first, "Assistant", "external_api", {"endpoint": "https://example.test"})
    restored = repository.load_project_configuration(context, first)
    assert restored["dataset_records"] == [{"case_id": "current"}]
    assert restored["external_target_config"]["endpoint"] == "https://example.test"
    assert repository.load_project_configuration(context, second)["external_target_config"] == {}
    outsider = repository.create_workspace("other@example.com", "Other")
    with pytest.raises(AuthorizationError):
        repository.load_project_configuration(outsider, first)


def test_duplicate_result_persistence_is_idempotent_under_concurrent_retries(tmp_path):
    repository = SQLiteRepository(tmp_path / "idempotency.sqlite3")
    context = repository.local_context()
    run_id = repository.create_run(
        context, run_name="Retry", model_name="model", mode="batch", unique_case_count=1, total_executions=1
    )
    result = {
        "case_id": "case-1",
        "question": "Question",
        "prompt_version": "p1",
        "target_version": "t1",
        "execution_status": "passed",
        "attempt_count": 3,
        "provider": "external",
        "overall_score": 0.5,
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        result_ids = list(pool.map(lambda _: repository.save_result(context, run_id, result), range(8)))
    assert len(set(result_ids)) == 1
    with repository.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM eval_results WHERE run_id = ?", (run_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 1
        assert conn.execute("SELECT completed_executions FROM eval_runs WHERE id = ?", (run_id,)).fetchone()[0] == 1
        execution = conn.execute(
            "SELECT attempt_count, provider FROM executions WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert execution["attempt_count"] == 3
        assert execution["provider"] == "external"


def test_identity_change_clears_previous_users_ui_memory_before_rendering(tmp_path, monkeypatch):
    repository = SQLiteRepository(tmp_path / "identity-change.sqlite3")
    database.set_repository(repository)
    first = repository.create_workspace("first@example.com", "First")
    second = repository.create_workspace("second@example.com", "Second")
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "authenticated")
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    monkeypatch.setattr(config, "AUTH_REQUIRE_ISSUED_AT", False)
    monkeypatch.setenv("AUTH_TRUSTED_PROXY", "true")
    monkeypatch.delenv("AUTH_ALLOWED_EMAIL_DOMAIN", raising=False)
    state = {}
    database.initialize_session(
        state, {"X-Auth-Subject": "email:first@example.com", "X-Auth-Email": "first@example.com"}
    )
    state.update(documents=["first-private-content"], provider_api_keys={"openai": "first-private-key"})
    with pytest.raises(AuthenticationError, match="identity changed"):
        database.initialize_session(
            state, {"X-Auth-Subject": "email:second@example.com", "X-Auth-Email": "second@example.com"}
        )
    assert state == {}
    assert first.workspace_id != second.workspace_id
    database.set_repository(None)


def test_retrieval_restores_only_latest_document_version_and_keeps_history(tmp_path):
    repository = SQLiteRepository(tmp_path / "corpus.sqlite3")
    context = repository.local_context()
    project = repository.create_project(context, {"name": "Project"})
    for index, content in enumerate(("Outdated policy", "Current policy"), start=1):
        repository.save_documents_and_chunks(
            context,
            [{"filename": "policy.md", "text": content}],
            [
                {
                    "filename": "policy.md",
                    "source_name": "policy",
                    "chunk_text": content,
                    "chunk_index": 0,
                    "chunk_id": f"policy-{index}",
                }
            ],
            project,
        )
    assert [chunk["chunk_text"] for chunk in repository.load_chunks(context, project)] == ["Current policy"]
    with repository.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM document_versions").fetchone()[0] == 2
