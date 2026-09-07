from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import Context

import pytest

from src import config, database
from src.auth import AuthenticationError
from src.domain import WorkspaceContext
from src.public_sessions import cleanup_expired_sessions, end_public_session, initialize_session
from src.review import ReviewService
from src.security import AuthorizationError
from src.storage import SQLiteRepository
from src.targets import SecretResolver, TargetConfigurationError


@pytest.fixture
def public_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUTH_MODE", "public-session")
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "PUBLIC_SESSION_TTL_SECONDS", 86400)
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "must-not-create.sqlite3")
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{config.DATABASE_PATH}")
    database.set_repository(None)
    states = []

    def create():
        state = {}
        states.append(state)
        return state, initialize_session(state, {}, temporary_root=tmp_path)

    yield create
    for state in states:
        end_public_session(state)
    database.set_repository(None)


def test_public_access_requires_explicit_binding_and_never_opens_configured_db(public_mode):
    with pytest.raises(AuthenticationError, match="Initialize"):
        database.current_context()
    with pytest.raises(AuthenticationError, match="Initialize"):
        database.init_db()
    state, session = public_mode()
    assert session.ephemeral and "Export" in session.notice
    assert not config.DATABASE_PATH.exists()
    assert session.repository.path.parent.stat().st_mode & 0o777 == 0o700
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 1
    with pytest.raises(PermissionError, match="another database"):
        database.connect(config.DATABASE_PATH)
    with pytest.raises(AuthorizationError):
        database.save_project({"name": "stale local identity"}, WorkspaceContext(1, 1))
    end_public_session(state)
    assert not config.DATABASE_PATH.exists()


def test_rerun_rebinds_own_repository_and_preserves_existing_session(public_mode):
    first_state, first = public_mode()
    database.save_project({"name": "First private work"})
    _, second = public_mode()
    database.save_project({"name": "Second private work"})
    assert first.context != second.context
    assert first.repository.path != second.repository.path
    again = initialize_session(first_state, {})
    assert not again.new_session
    assert database.get_repository() is first.repository
    assert database.current_context() == first.context
    assert [p["name"] for p in first.repository.list_projects(first.context)] == ["First private work"]
    with pytest.raises(AuthorizationError):
        database.save_project({"name": "wrong context"}, second.context)


def test_concurrent_visitors_write_read_export_and_reset_independently(public_mode):
    first_state, first = public_mode()
    second_state, second = public_mode()
    barrier = threading.Barrier(2)

    def visit(state, name, reset):
        initialize_session(state, {})
        project_id = database.save_project({"name": name})
        database.save_documents_and_chunks(
            [{"filename": f"{name}.md", "text": name}],
            [{"filename": f"{name}.md", "source_name": name, "chunk_text": name, "chunk_index": 0}],
            project_id,
        )
        run_id = database.create_eval_run(name, "mock-model", "demo", 1, project_id)
        database.save_eval_result(
            run_id,
            {"case_id": name, "question": name, "actual_answer": name, "execution_status": "passed"},
        )
        repository = database.get_repository()
        with repository.connection() as conn:
            execution_id = conn.execute("SELECT id FROM executions").fetchone()[0]
        ReviewService(repository).add_comment(database.current_context(), execution_id, f"Review {name}")
        database.record_export("json", name, run_id)
        barrier.wait(timeout=10)
        assert database.documents_df(project_id)["filename"].tolist() == [f"{name}.md"]
        assert database.eval_runs_df()["run_name"].tolist() == [name]
        if reset:
            database.reset_current_workspace(confirm=True)
        barrier.wait(timeout=10)
        return database.documents_df(None if reset else project_id), database.eval_runs_df()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(visit, first_state, "alpha", True)
        second_future = pool.submit(visit, second_state, "beta", False)
        first_documents, first_runs = first_future.result()
        second_documents, second_runs = second_future.result()
    assert first_documents.empty and first_runs.empty
    assert second_documents["filename"].tolist() == ["beta.md"]
    assert second_runs["run_name"].tolist() == ["beta"]
    with second.repository.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM exports").fetchone()[0] == 1
        assert conn.execute("SELECT body FROM comments").fetchone()[0] == "Review beta"
    assert not first.repository.list_projects(first.context)


def test_explicit_delete_erases_only_own_files_and_session_keys(public_mode):
    first_state, first = public_mode()
    _, second = public_mode()
    database.save_project({"name": "Keep this"})
    first_state["provider_api_keys"] = {"openai": "private-session-key"}
    first_directory = first.repository.path.parent
    end_public_session(first_state)
    assert first_state == {} and not first_directory.exists()
    assert second.repository.list_projects(second.context)[0]["name"] == "Keep this"


def test_idle_expiry_removes_data_and_rerun_starts_fresh(public_mode, monkeypatch):
    state, first = public_mode()
    database.save_project({"name": "Expires"})
    state["provider_api_keys"] = {"openai": "expired-key"}
    monkeypatch.setattr(config, "PUBLIC_SESSION_TTL_SECONDS", 10)
    assert cleanup_expired_sessions(now=state["_studio_private_session"].last_used + 11) >= 1
    assert not first.repository.path.parent.exists()
    second = initialize_session(state, {})
    assert second.new_session and second.context != first.context
    assert "provider_api_keys" not in state
    assert not second.repository.list_projects(second.context)


def test_background_worker_requires_explicit_repository_context_pair(public_mode):
    _, session = public_mode()

    def without_binding():
        with pytest.raises(AuthenticationError):
            database.save_project({"name": "Implicit access"})

    def with_binding():
        with database.request_scope(session.repository, session.context):
            database.save_project({"name": "Explicit worker"})
        with pytest.raises(AuthenticationError):
            database.current_context()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(without_binding).result()
        pool.submit(with_binding).result()
    assert session.repository.list_projects(session.context)[0]["name"] == "Explicit worker"


def test_public_session_cannot_implicitly_use_server_provider_or_target_keys(public_mode, monkeypatch):
    monkeypatch.setattr(config, "PROVIDER_API_KEYS", {"openai": "server-provider-key"})
    monkeypatch.setenv("PRIVATE_TARGET_KEY", "server-target-key")
    assert config.api_key_for_provider("openai") == ""
    assert config.available_models(provider="openai") == ["mock-model"]
    assert len(config.available_models("visitor-key", "openai")) > 1
    for supplied in (None, {"PRIVATE_TARGET_KEY": ""}):
        with pytest.raises(TargetConfigurationError, match="not configured"):
            SecretResolver(supplied).resolve("secret://PRIVATE_TARGET_KEY")
    assert SecretResolver({"PRIVATE_TARGET_KEY": "visitor-key"}).resolve("secret://PRIVATE_TARGET_KEY") == "visitor-key"


def test_production_single_user_facade_and_hook_refuse_even_previously_bound_context(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    monkeypatch.setattr(config, "APP_ENV", "development")
    repository = SQLiteRepository(tmp_path / "development.sqlite3")
    database.set_repository(repository)
    development_context = database.current_context()
    monkeypatch.setattr(config, "APP_ENV", "production")
    with pytest.raises(AuthenticationError, match="disabled in production"):
        database.current_context()
    with pytest.raises(AuthenticationError, match="disabled in production"):
        database.save_project({"name": "Cannot bypass via explicit context"}, development_context)
    state = {"private_data": "previous identity"}
    with pytest.raises(AuthenticationError, match="disabled in production"):
        initialize_session(state, {})
    assert not state
    database.set_repository(None)


def test_authenticated_requests_never_inherit_another_context(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "AUTH_REQUIRE_ISSUED_AT", False)
    monkeypatch.setenv("AUTH_TRUSTED_PROXY", "true")
    repository = SQLiteRepository(tmp_path / "authenticated.sqlite3")
    contexts = [repository.create_workspace(f"{name}@example.com", name) for name in ("one", "two")]
    barrier = threading.Barrier(2)

    def visit(index):
        database.set_repository(repository)
        name = ("one", "two")[index]
        headers = {"x-auth-subject": f"email:{name}@example.com", "x-auth-email": f"{name}@example.com"}
        assert database.current_context(headers) == contexts[index]
        barrier.wait(timeout=10)
        database.save_project({"name": name})
        assert database.current_context() == contexts[index]
        with pytest.raises(AuthenticationError):
            database.current_context({})
        with pytest.raises(AuthenticationError):
            database.current_context()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(visit, (0, 1)))
    for index, name in enumerate(("one", "two")):
        assert repository.list_projects(contexts[index])[0]["name"] == name
    assert Context().run(lambda: database._request.get()) is None


def test_an_existing_configured_database_is_untouched(public_mode):
    path = config.DATABASE_PATH
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE sentinel (value TEXT)")
        conn.execute("INSERT INTO sentinel VALUES ('keep')")
    before = path.read_bytes()
    state, _ = public_mode()
    database.save_project({"name": "Private"})
    database.reset_current_workspace(confirm=True)
    end_public_session(state)
    assert path.read_bytes() == before


def test_reauthenticated_identity_switch_discards_previous_ui_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "AUTH_REQUIRE_ISSUED_AT", False)
    monkeypatch.setenv("AUTH_TRUSTED_PROXY", "true")
    repository = SQLiteRepository(tmp_path / "identity-switch.sqlite3")
    first = repository.create_workspace("first@example.com", "First")
    second = repository.create_workspace("second@example.com", "Second")
    database.set_repository(repository)
    state = {"workspace_context": first, "documents": ["first visitor data"], "provider_api_keys": {"openai": "key"}}
    result = initialize_session(
        state,
        {"x-auth-subject": "email:second@example.com", "x-auth-email": "second@example.com"},
    )
    assert result.context == second and not result.ephemeral
    assert state == {"workspace_context": second}
    with pytest.raises(AuthenticationError):
        initialize_session(state, {})
    assert state == {}
    database.set_repository(None)
