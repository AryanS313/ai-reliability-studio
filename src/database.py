"""Backward-compatible database facade over workspace-scoped repositories.

New services should depend on `src.storage.Repository` directly. This module keeps
the original Streamlit/function API while ensuring every operation is scoped to
the explicit local development workspace.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from src import config
from src.domain import WorkspaceContext
from src.migrations import migrate_sqlite
from src.storage import repository_from_url
from src.versioning import version_hash

_repository = None
_active_context: WorkspaceContext | None = None


def get_repository():
    global _repository
    if _repository is None:
        _repository = repository_from_url()
    return _repository


def set_repository(repository) -> None:
    global _active_context, _repository
    _repository = repository
    _active_context = None


def current_context(headers: dict[str, Any] | None = None) -> WorkspaceContext:
    global _active_context
    if headers is None and _active_context is not None:
        return _active_context
    repository = get_repository()
    if config.AUTH_MODE == "single-user":
        context = repository.local_context()
        _active_context = context
        return context
    from src.auth import authenticate_request, workspace_context

    context = workspace_context(repository, authenticate_request(headers), None)
    _active_context = context
    return context


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
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
