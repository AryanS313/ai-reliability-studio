"""Backward-compatible database facade over workspace-scoped repositories.

New services should depend on `src.storage.Repository` directly. This module keeps
the original Streamlit/function API while ensuring every operation is scoped to
the repository and workspace bound to the current execution context.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src import config
from src.domain import WorkspaceContext
from src.migrations import migrate_sqlite
from src.storage import Repository, SQLiteRepository, repository_from_url
from src.versioning import version_hash


@dataclass(frozen=True)
class RequestBinding:
    repository: Repository
    context: WorkspaceContext
    auth_mode: str
    app_env: str


_repository: ContextVar[Any] = ContextVar("studio_repository", default=None)
_request: ContextVar[RequestBinding | None] = ContextVar("studio_request", default=None)


def get_repository():
    if config.AUTH_MODE == "single-user" and config.APP_ENV == "production":
        from src.auth import authenticate_request

        clear_request()
        authenticate_request()
    binding = _valid_binding()
    if binding is not None:
        return binding.repository
    if config.public_sessions_enabled():
        from src.auth import AuthenticationError

        raise AuthenticationError("Initialize a private public session before accessing storage.")
    repository = _repository.get()
    if repository is None:
        repository = repository_from_url()
        _repository.set(repository)
    return repository


def set_repository(repository) -> None:
    """Override storage in this execution context only (CLI and direct tests)."""
    _repository.set(repository)
    _request.set(None)


def clear_request() -> None:
    """End the current request; never retain a prior visitor's identity."""
    _request.set(None)


def _valid_binding() -> RequestBinding | None:
    binding = _request.get()
    if binding is not None and (binding.auth_mode, binding.app_env) != (config.AUTH_MODE, config.APP_ENV):
        clear_request()
        return None
    return binding


def bind_context(repository: Repository, context: WorkspaceContext) -> RequestBinding:
    """Bind an already authorized repository/context pair to the current request.

    Callers must obtain the pair from authentication or a private public session.
    Workers must receive that pair explicitly and use request_scope; a new thread
    intentionally inherits neither the previous request nor its database.
    """
    if config.AUTH_MODE == "single-user" and config.APP_ENV == "production":
        from src.auth import authenticate_request

        authenticate_request()
    repository.authorize(context)
    binding = RequestBinding(repository, context, config.AUTH_MODE, config.APP_ENV)
    _request.set(binding)
    return binding


@contextmanager
def request_scope(repository: Repository, context: WorkspaceContext) -> Iterator[RequestBinding]:
    """Explicit, nesting-safe binding for a worker or request with a known identity."""
    previous = _request.set(None)
    try:
        yield bind_context(repository, context)
    finally:
        _request.reset(previous)


def current_context(headers: dict[str, Any] | None = None) -> WorkspaceContext:
    from src.auth import AuthenticationError, authenticate_request, workspace_context

    # Check this even for an existing binding; production must never inherit the
    # permissive development single-user path.
    if config.AUTH_MODE == "single-user" and config.APP_ENV == "production":
        clear_request()
        authenticate_request(headers)
    binding = _valid_binding()
    if config.public_sessions_enabled():
        if binding is None:
            raise AuthenticationError("Initialize a private public session before accessing storage.")
        return binding.context
    if headers is None and binding is not None:
        return binding.context
    clear_request()
    identity = authenticate_request(headers)
    repository = get_repository()
    context = workspace_context(repository, identity, None)
    bind_context(repository, context)
    return context


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    if config.public_sessions_enabled():
        repository = get_repository()
        if not isinstance(repository, SQLiteRepository):
            raise RuntimeError("Public sessions require private SQLite storage.")
        if db_path is not None and Path(db_path).resolve() != repository.path.resolve():
            raise PermissionError("Public sessions cannot connect to another database.")
        path = repository.path
    else:
        path = Path(db_path or config.DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    if conn is not None:
        migrate_sqlite(conn)
        conn.commit()
        return
    get_repository().migrate()


def save_project(metadata: dict[str, str], context: WorkspaceContext | None = None) -> int:
    return get_repository().create_project(context or current_context(), metadata)


def clear_database() -> None:
    raise RuntimeError(
        "Global database reset was removed. Use reset_current_workspace(confirm=True) with an authorized owner."
    )


def reset_current_workspace(*, confirm: bool, context: WorkspaceContext | None = None) -> None:
    if not confirm:
        raise ValueError("Workspace reset requires explicit confirmation.")
    get_repository().reset_workspace(context or current_context())


def clear_results(*, confirm: bool = False, context: WorkspaceContext | None = None) -> None:
    if not confirm:
        raise ValueError("Clearing evaluation results requires explicit confirmation.")
    get_repository().clear_results(context or current_context())


def save_documents_and_chunks(
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    project_id: int | None = None,
    context: WorkspaceContext | None = None,
) -> list[int]:
    return get_repository().save_documents_and_chunks(
        context or current_context(), documents, chunks, project_id=project_id
    )


def load_chunks(
    project_id: int | None = None,
    context: WorkspaceContext | None = None,
) -> list[dict[str, Any]]:
    return get_repository().load_chunks(context or current_context(), project_id=project_id)


def documents_df(
    project_id: int | None = None,
    context: WorkspaceContext | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(get_repository().list_documents(context or current_context(), project_id=project_id))


def save_prompt(
    project_id: int | None,
    prompt_name: str,
    prompt_text: str,
    prompt_type: str,
    context: WorkspaceContext | None = None,
    *,
    explanation: str = "",
    motivated_by_failures: list[str] | None = None,
) -> int:
    return get_repository().save_prompt(
        context or current_context(),
        project_id,
        prompt_name,
        prompt_text,
        prompt_type,
        explanation=explanation,
        motivated_by_failures=motivated_by_failures,
    )


def prompts_df(
    project_id: int | None = None,
    context: WorkspaceContext | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(get_repository().list_prompts(context or current_context(), project_id=project_id))


def create_eval_run(
    run_name: str,
    model_name: str,
    mode: str,
    total_questions: int,
    project_id: int | None = None,
    notes: str = "",
    *,
    total_executions: int | None = None,
    target_type: str = "synthetic_mock",
    target_version: str | None = None,
    dataset_version_id: int | None = None,
    manifest: dict[str, Any] | None = None,
    evaluator_version: str | None = None,
    label_semantics_version: str | None = None,
    threshold_version: str | None = None,
    calibration_status: str = "insufficiently_calibrated",
    calibration_version: str | None = None,
    context: WorkspaceContext | None = None,
) -> int:
    return get_repository().create_run(
        context or current_context(),
        run_name=run_name,
        model_name=model_name,
        mode=mode,
        unique_case_count=total_questions,
        total_executions=total_executions or total_questions,
        project_id=project_id,
        notes=notes,
        target_type=target_type,
        target_version=target_version,
        dataset_version_id=dataset_version_id,
        manifest=manifest,
        evaluator_version=evaluator_version,
        label_semantics_version=label_semantics_version,
        threshold_version=threshold_version,
        calibration_status=calibration_status,
        calibration_version=calibration_version,
    )


def save_eval_result(
    run_id: int,
    result: dict[str, Any],
    context: WorkspaceContext | None = None,
) -> int:
    return get_repository().save_result(context or current_context(), run_id, result)


def record_export(
    report_format: str,
    content: str,
    run_id: int | None = None,
    context: WorkspaceContext | None = None,
) -> int:
    return get_repository().record_export(
        context or current_context(), report_format, version_hash(content), run_id=run_id
    )


def latest_results_df(context: WorkspaceContext | None = None) -> pd.DataFrame:
    return pd.DataFrame(get_repository().latest_results(context or current_context()))


def all_results_df(context: WorkspaceContext | None = None) -> pd.DataFrame:
    return pd.DataFrame(get_repository().list_results(context or current_context()))


def eval_runs_df(context: WorkspaceContext | None = None) -> pd.DataFrame:
    return pd.DataFrame(get_repository().list_runs(context or current_context()))
