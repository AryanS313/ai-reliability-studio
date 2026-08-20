from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from psycopg.errors import InsufficientPrivilege

from src.domain import Role, WorkspaceContext
from src.security import AuthorizationError
from src.storage import PostgresRepository

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_repository():
    database_url = os.getenv("TEST_POSTGRES_URL", "")
    if not database_url:
        pytest.skip("Set TEST_POSTGRES_URL to run the optional PostgreSQL integration profile.")
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
    repository = PostgresRepository(database_url)
    repository.migrate()
    yield repository
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


def test_clean_migration_and_idempotent_existing_database_upgrade(postgres_repository):
    repository = postgres_repository
    context = repository.create_workspace("migration@example.com", "Migration")
    project_id = repository.create_project(context, {"name": "Preserved project"})
    repository.migrate()
    assert repository.list_projects(context)[0]["id"] == project_id
    with repository.connection() as conn:
        versions = {int(row["version"]) for row in conn.execute("SELECT version FROM schema_migrations")}
        columns = {
            str(row["column_name"])
            for row in conn.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'users'
                """
            )
        }
    assert {1, 7}.issubset(versions)
    assert {"disabled_at", "session_not_before"}.issubset(columns)


def test_row_level_security_and_unauthorized_cross_workspace_access(postgres_repository):
    repository = postgres_repository
    first = repository.create_workspace("rls-first@example.com", "RLS First")
    second = repository.create_workspace("rls-second@example.com", "RLS Second")
    repository.create_project(first, {"name": "First private project"})
    repository.create_project(second, {"name": "Second private project"})

    role_name = "ars_rls_verifier"
    with repository.connection() as conn:
        conn.execute(f"DROP ROLE IF EXISTS {role_name}")
        conn.execute(f"CREATE ROLE {role_name} NOLOGIN")
        conn.execute(f"GRANT USAGE ON SCHEMA public TO {role_name}")
        conn.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role_name}")
        conn.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role_name}")

    with repository.connection() as conn:
        conn.execute(f"SET ROLE {role_name}")
        conn.execute("SELECT set_config('ars.user_id', %s, true)", (str(first.user_id),))
        conn.execute("SELECT set_config('ars.workspace_id', %s, true)", (str(first.workspace_id),))
        names = [row["name"] for row in conn.execute("SELECT name FROM projects ORDER BY name")]
        assert names == ["First private project"]
    with pytest.raises(InsufficientPrivilege):
        with repository.connection() as conn:
            conn.execute(f"SET ROLE {role_name}")
            conn.execute("SELECT set_config('ars.user_id', %s, true)", (str(first.user_id),))
            conn.execute("SELECT set_config('ars.workspace_id', %s, true)", (str(first.workspace_id),))
            conn.execute(
                "INSERT INTO projects (workspace_id, name) VALUES (%s, 'forged')",
                (second.workspace_id,),
            )

    with repository.connection() as conn:
        conn.execute(f"DROP OWNED BY {role_name}")
        conn.execute(f"DROP ROLE {role_name}")


def test_transaction_rollback_concurrent_run_writes_and_immutable_versions(postgres_repository):
    repository = postgres_repository
    context = repository.create_workspace("concurrency@example.com", "Concurrency")
    project_id = repository.create_project(context, {"name": "Concurrent project"})
    with pytest.raises(RuntimeError):
        with repository.connection() as conn:
            conn.execute("INSERT INTO workspaces (name) VALUES ('must rollback')")
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
        run_ids = list(pool.map(create_run, range(12)))
    assert len(set(run_ids)) == 12

    first_version = repository.save_prompt(context, project_id, "Prompt", "Immutable content", "candidate")
    same_version = repository.save_prompt(context, project_id, "Prompt", "Immutable content", "candidate")
    changed_version = repository.save_prompt(context, project_id, "Prompt", "New immutable content", "candidate")
    assert first_version == same_version
    assert changed_version != first_version

    with repository.connection() as conn:
        audit_rows = conn.execute(
            "SELECT user_id, workspace_id, action FROM audit_logs WHERE workspace_id = %s",
            (context.workspace_id,),
        ).fetchall()
    assert audit_rows
    assert all(int(row["user_id"]) == context.user_id for row in audit_rows)


def test_repository_authorization_rejects_forged_context(postgres_repository):
    repository = postgres_repository
    first = repository.create_workspace("authz-first@example.com", "Authz First")
    second = repository.create_workspace("authz-second@example.com", "Authz Second")
    forged = WorkspaceContext(first.user_id, second.workspace_id, Role.OWNER)
    with pytest.raises(AuthorizationError):
        repository.create_project(forged, {"name": "forged"})
