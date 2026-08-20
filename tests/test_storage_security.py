from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.domain import Role, WorkspaceContext
from src.security import AuthorizationError, UploadSecurityError, redact_pii, redact_secrets, sanitize_filename
from src.storage import SQLiteRepository


def test_migration_preserves_legacy_data_and_never_drops(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, use_case TEXT, industry TEXT, notes TEXT, created_at TEXT NOT NULL);
        CREATE TABLE sentinel (value TEXT NOT NULL);
        INSERT INTO projects VALUES (42, 'Legacy', '', '', '', '2024-01-01');
        INSERT INTO sentinel VALUES ('keep-me');
        """
    )
    conn.commit()
    conn.close()
    repository = SQLiteRepository(path)
    repository.migrate()
    repository.migrate()
    with repository.connection() as migrated:
        assert migrated.execute("SELECT name FROM projects WHERE id = 42").fetchone()["name"] == "Legacy"
        assert migrated.execute("SELECT value FROM sentinel").fetchone()["value"] == "keep-me"
        assert migrated.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert migrated.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 7


def test_workspace_isolation_for_reads_writes_deletes_and_exports(tmp_path):
    repository = SQLiteRepository(tmp_path / "isolated.sqlite3")
    first = repository.create_workspace("first@example.com", "First")
    second = repository.create_workspace("second@example.com", "Second")
    first_project = repository.create_project(first, {"name": "First secret project"})
    repository.create_project(second, {"name": "Second project"})
    assert [item["name"] for item in repository.list_projects(first)] == ["First secret project"]
    assert [item["name"] for item in repository.list_projects(second)] == ["Second project"]
    with pytest.raises(AuthorizationError):
        repository.save_documents_and_chunks(
            second,
            [{"filename": "secret.md", "text": "secret"}],
            [],
            project_id=first_project,
        )
    repository.clear_results(second)
    assert repository.list_projects(first)[0]["id"] == first_project
    repository.reset_workspace(second)
    assert repository.list_projects(first)[0]["name"] == "First secret project"


def test_export_is_scoped_to_the_active_workspace(tmp_path):
    repository = SQLiteRepository(tmp_path / "exports.sqlite3")
    first = repository.create_workspace("first@example.com", "First")
    second = repository.create_workspace("second@example.com", "Second")
    run_id = repository.create_run(
        first,
        run_name="private run",
        model_name="model",
        mode="batch",
        unique_case_count=1,
        total_executions=1,
    )
    assert repository.record_export(first, "json", "content-hash", run_id) > 0
    with pytest.raises(AuthorizationError):
        repository.record_export(second, "json", "content-hash", run_id)
    repository.clear_results(first)
    with repository.connection() as conn:
        assert (
            conn.execute("SELECT run_id FROM exports WHERE workspace_id = ?", (first.workspace_id,)).fetchone()[0]
            is None
        )


def test_run_cannot_reference_another_workspaces_dataset_version(tmp_path):
    repository = SQLiteRepository(tmp_path / "dataset-scope.sqlite3")
    first = repository.create_workspace("first@example.com", "First")
    second = repository.create_workspace("second@example.com", "Second")
    first_project = repository.create_project(first, {"name": "First"})
    second_project = repository.create_project(second, {"name": "Second"})
    dataset_version = repository.create_dataset_version(
        first,
        first_project,
        "Private dataset",
        [{"case_id": "private-case", "question": "Private"}],
    )
    with pytest.raises(AuthorizationError):
        repository.create_run(
            second,
            run_name="forged run",
            model_name="model",
            mode="batch",
            unique_case_count=1,
            total_executions=1,
            project_id=second_project,
            dataset_version_id=dataset_version,
        )


def test_role_authorization_and_cross_workspace_context_rejected(tmp_path):
    repository = SQLiteRepository(tmp_path / "roles.sqlite3")
    owner = repository.create_workspace("owner@example.com", "Workspace")
    viewer_id = repository.add_member(owner, "viewer@example.com", Role.VIEWER)
    viewer = WorkspaceContext(viewer_id, owner.workspace_id, Role.VIEWER)
    with pytest.raises(AuthorizationError):
        repository.create_project(viewer, {"name": "not allowed"})
    foreign = repository.create_workspace("foreign@example.com", "Foreign")
    forged = WorkspaceContext(viewer_id, foreign.workspace_id, Role.VIEWER)
    with pytest.raises(AuthorizationError):
        repository.list_projects(forged)


def test_secret_and_filename_protection():
    assert sanitize_filename("../../customer policy.md") == "customer policy.md"
    with pytest.raises(UploadSecurityError):
        sanitize_filename("../..")
    value = redact_secrets({"api_key": "sk-secret-value-123456", "safe": 3})
    assert value == {"api_key": "[REDACTED]", "safe": 3}
    assert "user@example.com" not in redact_pii("Contact user@example.com")


def test_audit_metadata_redacts_secret_references(tmp_path):
    repository = SQLiteRepository(tmp_path / "audit-redaction.sqlite3")
    context = repository.create_workspace("owner@example.com", "Workspace")
    repository.audit(context, "security.test", "workspace", str(context.workspace_id), {"token": "secret://TOKEN"})
    with repository.connection() as conn:
        metadata = conn.execute("SELECT metadata_json FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert "TOKEN" not in metadata
    assert "[REDACTED]" in metadata


def test_target_versions_refuse_raw_secret_storage(tmp_path):
    repository = SQLiteRepository(tmp_path / "targets.sqlite3")
    context = repository.create_workspace("owner@example.com", "Workspace")
    project = repository.create_project(context, {"name": "Project"})
    with pytest.raises(ValueError, match="raw secret"):
        repository.create_target_version(
            context,
            project,
            "Unsafe target",
            "external_api",
            {"headers": {"Authorization": "sk-secret-value-123456789"}},
        )
    version_id = repository.create_target_version(
        context,
        project,
        "Safe target",
        "external_api",
        {"headers": {"Authorization": "secret://TOKEN"}},
    )
    assert version_id > 0
    with repository.connection() as conn:
        stored = conn.execute("SELECT configuration_json FROM target_versions WHERE id = ?", (version_id,)).fetchone()[
            0
        ]
    assert "sk-secret" not in stored


def test_sqlite_transactions_rollback_and_concurrent_run_writes_are_integral(tmp_path):
    repository = SQLiteRepository(tmp_path / "transactions.sqlite3")
    context = repository.create_workspace("owner@example.com", "Transactions")
    project_id = repository.create_project(context, {"name": "Project"})
    with pytest.raises(RuntimeError, match="force rollback"):
        with repository.connection() as conn:
            conn.execute(
                "INSERT INTO workspaces (name, retention_days, pii_redaction_enabled, created_at) VALUES (?, 90, 0, ?)",
                ("must rollback", "2026-08-20T00:00:00+00:00"),
            )
            raise RuntimeError("force rollback")
    with repository.connection() as conn:
        assert conn.execute("SELECT id FROM workspaces WHERE name = 'must rollback'").fetchone() is None

    def create_run(index: int) -> int:
        return repository.create_run(
            context,
            run_name=f"concurrent-{index}",
            model_name="model",
            mode="batch",
            unique_case_count=1,
            total_executions=1,
            project_id=project_id,
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        run_ids = list(pool.map(create_run, range(16)))
    assert len(set(run_ids)) == 16
    with repository.connection() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM eval_runs WHERE workspace_id = ?", (context.workspace_id,)).fetchone()[0]
            == 16
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE workspace_id = ? AND action = 'run.create'",
                (context.workspace_id,),
            ).fetchone()[0]
            == 16
        )


def test_revoked_membership_fails_authorization_and_prompt_versions_are_immutable(tmp_path):
    repository = SQLiteRepository(tmp_path / "revocation.sqlite3")
    context = repository.create_workspace("owner@example.com", "Revocation")
    project_id = repository.create_project(context, {"name": "Project"})
    first = repository.save_prompt(context, project_id, "Prompt", "Immutable content", "candidate")
    same = repository.save_prompt(context, project_id, "Prompt", "Immutable content", "candidate")
    changed = repository.save_prompt(context, project_id, "Prompt", "Changed content", "candidate")
    assert first == same
    assert changed != first
    with repository.connection() as conn:
        original = conn.execute("SELECT content FROM prompt_versions WHERE id = ?", (first,)).fetchone()[0]
        conn.execute(
            "UPDATE memberships SET revoked_at = ? WHERE user_id = ? AND workspace_id = ?",
            ("2026-08-20T00:00:00+00:00", context.user_id, context.workspace_id),
        )
    assert original == "Immutable content"
    with pytest.raises(AuthorizationError, match="does not belong"):
        repository.list_projects(context)
