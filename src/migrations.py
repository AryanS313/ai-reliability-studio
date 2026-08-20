from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

LATEST_SCHEMA_VERSION = 7


def migrate_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {int(row[0]) for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    migrations = {
        1: _migration_001,
        2: _migration_002,
        3: _migration_003,
        4: _migration_004,
        5: _migration_005,
        6: _migration_006,
        7: _migration_007,
    }
    for version, migration in migrations.items():
        if version in applied:
            continue
        with conn:
            migration(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(UTC).isoformat()),
            )


def _migration_001(conn: sqlite3.Connection) -> None:
    """Create legacy-compatible core tables without deleting existing data."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            use_case TEXT,
            industry TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'indexed',
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            source_name TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id)
        );
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            prompt_name TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            prompt_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS eval_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            run_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            model_name TEXT NOT NULL,
            mode TEXT NOT NULL,
            total_questions INTEGER NOT NULL,
            notes TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS eval_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            expected_answer TEXT,
            actual_answer TEXT,
            expected_source TEXT,
            retrieved_sources TEXT,
            retrieved_chunks TEXT,
            category TEXT,
            should_escalate INTEGER,
            actual_escalation INTEGER,
            expected_answer_match_score REAL,
            source_retrieval_score REAL,
            citation_correctness_score REAL,
            groundedness_score REAL,
            escalation_correctness_score REAL,
            hallucination_risk TEXT,
            latency_ms REAL,
            estimated_cost REAL,
            overall_score REAL,
            failure_type TEXT,
            suggested_fix TEXT,
            prompt_name TEXT,
            model_name TEXT,
            final_prompt TEXT,
            FOREIGN KEY(run_id) REFERENCES eval_runs(id)
        );
        """
    )


def _migration_002(conn: sqlite3.Connection) -> None:
    """Add identity, workspace isolation, immutable versions, and audit entities."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT,
            auth_subject TEXT UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            retention_days INTEGER NOT NULL DEFAULT 90,
            pii_redaction_enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memberships (
            user_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner','admin','editor','reviewer','viewer')),
            created_at TEXT NOT NULL,
            PRIMARY KEY(user_id, workspace_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS document_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            extraction_warnings TEXT NOT NULL DEFAULT '[]',
            text_preview TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(document_id, version),
            UNIQUE(document_id, content_hash),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(document_id) REFERENCES documents(id)
        );
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            prompt_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            change_explanation TEXT,
            motivated_by_failures TEXT NOT NULL DEFAULT '[]',
            created_by INTEGER,
            created_at TEXT NOT NULL,
            promoted_at TEXT,
            UNIQUE(prompt_id, version),
            UNIQUE(prompt_id, content_hash),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(prompt_id) REFERENCES prompts(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS datasets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            project_id INTEGER,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(workspace_id, project_id, name),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS dataset_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            dataset_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            rows_json TEXT NOT NULL,
            case_count INTEGER NOT NULL,
            immutable INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(dataset_id, version),
            UNIQUE(dataset_id, content_hash),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            project_id INTEGER,
            name TEXT NOT NULL,
            target_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(workspace_id, project_id, name),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS target_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            version_hash TEXT NOT NULL,
            configuration_json TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(target_id, version),
            UNIQUE(target_id, version_hash),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(target_id) REFERENCES targets(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            run_id INTEGER NOT NULL,
            case_id TEXT NOT NULL,
            execution_key TEXT NOT NULL,
            prompt_version_id INTEGER,
            target_version_id INTEGER,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            completed_at TEXT,
            latency_ms REAL,
            http_status INTEGER,
            provider TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost REAL,
            error_code TEXT,
            safe_error TEXT,
            response_json TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(workspace_id, execution_key),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(run_id) REFERENCES eval_runs(id),
            FOREIGN KEY(prompt_version_id) REFERENCES prompt_versions(id),
            FOREIGN KEY(target_version_id) REFERENCES target_versions(id)
        );
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            execution_id INTEGER NOT NULL,
            evaluator_version TEXT NOT NULL,
            determination_state TEXT NOT NULL,
            confidence REAL,
            metrics_json TEXT NOT NULL,
            explanation_json TEXT NOT NULL,
            failure_labels TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(execution_id) REFERENCES executions(id)
        );
        CREATE TABLE IF NOT EXISTS judgments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            execution_id INTEGER NOT NULL,
            evaluator_type TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            prompt TEXT,
            prompt_hash TEXT,
            temperature REAL,
            output_json TEXT NOT NULL,
            confidence REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(execution_id) REFERENCES executions(id)
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            execution_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            parent_id INTEGER,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(execution_id) REFERENCES executions(id),
            FOREIGN KEY(author_id) REFERENCES users(id),
            FOREIGN KEY(parent_id) REFERENCES comments(id)
        );
        CREATE TABLE IF NOT EXISTS review_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            execution_id INTEGER NOT NULL,
            reviewer_id INTEGER,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'needs_review',
            human_score REAL,
            automated_disagreement INTEGER NOT NULL DEFAULT 0,
            decision TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(execution_id) REFERENCES executions(id),
            FOREIGN KEY(reviewer_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS exports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            run_id INTEGER,
            format TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(run_id) REFERENCES eval_runs(id)
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS execution_cache (
            workspace_id INTEGER NOT NULL,
            cache_key TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            PRIMARY KEY(workspace_id, cache_key),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS scheduled_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            schedule TEXT NOT NULL,
            configuration_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        """
    )
    for table in ["projects", "documents", "chunks", "prompts", "eval_runs", "eval_results"]:
        _ensure_column(conn, table, "workspace_id", "INTEGER")
    _ensure_column(conn, "documents", "safe_filename", "TEXT")
    _ensure_column(conn, "documents", "content_hash", "TEXT")
    _ensure_column(conn, "chunks", "document_version_id", "INTEGER")
    _ensure_column(conn, "chunks", "filename", "TEXT")
    _ensure_column(conn, "chunks", "chunk_id", "TEXT")
    _ensure_column(conn, "chunks", "page", "INTEGER")
    _ensure_column(conn, "chunks", "section", "TEXT")
    _ensure_column(conn, "chunks", "text_start", "INTEGER")
    _ensure_column(conn, "chunks", "text_end", "INTEGER")
    _ensure_column(conn, "chunks", "content_hash", "TEXT")
    _ensure_column(conn, "prompts", "current_version_id", "INTEGER")
    for column, definition in [
        ("status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("target_type", "TEXT NOT NULL DEFAULT 'synthetic_mock'"),
        ("target_version", "TEXT"),
        ("dataset_version_id", "INTEGER"),
        ("manifest_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("unique_case_count", "INTEGER NOT NULL DEFAULT 0"),
        ("total_executions", "INTEGER NOT NULL DEFAULT 0"),
        ("completed_executions", "INTEGER NOT NULL DEFAULT 0"),
        ("cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        _ensure_column(conn, "eval_runs", column, definition)

    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, display_name, auth_subject, created_at) VALUES (1, ?, ?, ?, ?)",
        ("local@ai-reliability-studio.invalid", "Local User", "local-user", now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO workspaces (id, name, retention_days, pii_redaction_enabled, created_at) VALUES (1, ?, 90, 0, ?)",
        ("Local Workspace", now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO memberships (user_id, workspace_id, role, created_at) VALUES (1, 1, 'owner', ?)",
        (now,),
    )
    conn.execute("UPDATE projects SET workspace_id = 1 WHERE workspace_id IS NULL")
    conn.execute(
        "UPDATE documents SET workspace_id = COALESCE((SELECT workspace_id FROM projects WHERE projects.id = documents.project_id), 1) WHERE workspace_id IS NULL"
    )
    conn.execute("UPDATE documents SET safe_filename = filename WHERE safe_filename IS NULL")
    conn.execute(
        "UPDATE chunks SET workspace_id = COALESCE((SELECT workspace_id FROM documents WHERE documents.id = chunks.document_id), 1) WHERE workspace_id IS NULL"
    )
    conn.execute(
        "UPDATE prompts SET workspace_id = COALESCE((SELECT workspace_id FROM projects WHERE projects.id = prompts.project_id), 1) WHERE workspace_id IS NULL"
    )
    conn.execute(
        "UPDATE eval_runs SET workspace_id = COALESCE((SELECT workspace_id FROM projects WHERE projects.id = eval_runs.project_id), 1) WHERE workspace_id IS NULL"
    )
    conn.execute("UPDATE eval_runs SET unique_case_count = total_questions WHERE unique_case_count = 0")
    conn.execute(
        "UPDATE eval_results SET workspace_id = COALESCE((SELECT workspace_id FROM eval_runs WHERE eval_runs.id = eval_results.run_id), 1) WHERE workspace_id IS NULL"
    )
    _backfill_legacy_versions(conn, now)


def _migration_003(conn: sqlite3.Connection) -> None:
    """Enrich legacy results additively for reproducible scoring and status views."""
    additions = {
        "case_id": "TEXT",
        "severity": "TEXT NOT NULL DEFAULT 'medium'",
        "tags": "TEXT NOT NULL DEFAULT '[]'",
        "execution_status": "TEXT NOT NULL DEFAULT 'passed'",
        "error_code": "TEXT",
        "safe_error": "TEXT",
        "target_type": "TEXT NOT NULL DEFAULT 'synthetic_mock'",
        "target_version": "TEXT",
        "prompt_version": "TEXT",
        "citation_present": "INTEGER",
        "citation_source_valid": "INTEGER",
        "citation_supports_claim": "INTEGER",
        "citation_completeness": "REAL",
        "citation_details": "TEXT NOT NULL DEFAULT '[]'",
        "claim_assessments": "TEXT NOT NULL DEFAULT '[]'",
        "failure_labels": "TEXT NOT NULL DEFAULT '[]'",
        "evaluator_confidence": "REAL",
        "determination_state": "TEXT",
        "score_explanation": "TEXT NOT NULL DEFAULT '{}'",
        "actual_escalation_decision": "TEXT",
        "escalation_destination": "TEXT",
        "escalation_urgency": "TEXT",
        "escalation_reason": "TEXT",
        "input_tokens": "INTEGER",
        "output_tokens": "INTEGER",
        "http_status": "INTEGER",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for column, definition in additions.items():
        _ensure_column(conn, "eval_results", column, definition)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_projects_workspace ON projects(workspace_id);
        CREATE INDEX IF NOT EXISTS idx_documents_workspace_project ON documents(workspace_id, project_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_workspace_document ON chunks(workspace_id, document_id);
        CREATE INDEX IF NOT EXISTS idx_prompts_workspace_project ON prompts(workspace_id, project_id);
        CREATE INDEX IF NOT EXISTS idx_runs_workspace_timestamp ON eval_runs(workspace_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_results_workspace_run ON eval_results(workspace_id, run_id);
        CREATE INDEX IF NOT EXISTS idx_executions_workspace_run ON executions(workspace_id, run_id);
        CREATE INDEX IF NOT EXISTS idx_scores_workspace_execution ON scores(workspace_id, execution_id);
        CREATE INDEX IF NOT EXISTS idx_audit_workspace_created ON audit_logs(workspace_id, created_at);
        """
    )


def _migration_004(conn: sqlite3.Connection) -> None:
    """Persist evaluator semantics, thresholds, calibration, and structured evidence."""
    for column, definition in [
        ("evaluator_version", "TEXT"),
        ("label_semantics_version", "TEXT"),
        ("threshold_version", "TEXT"),
        ("calibration_status", "TEXT NOT NULL DEFAULT 'insufficiently_calibrated'"),
        ("calibration_version", "TEXT"),
    ]:
        _ensure_column(conn, "eval_runs", column, definition)
    for column, definition in [
        ("evaluator_version", "TEXT"),
        ("label_semantics_version", "TEXT"),
        ("threshold_version", "TEXT"),
        ("calibration_status", "TEXT NOT NULL DEFAULT 'insufficiently_calibrated'"),
        ("calibration_version", "TEXT"),
        ("failure_reason_codes", "TEXT NOT NULL DEFAULT '[]'"),
        ("failure_evidence", "TEXT NOT NULL DEFAULT '{}'"),
    ]:
        _ensure_column(conn, "eval_results", column, definition)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS calibration_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            dataset_version_id INTEGER,
            evaluator_version TEXT NOT NULL,
            threshold_version TEXT NOT NULL,
            calibration_version TEXT NOT NULL,
            status TEXT NOT NULL,
            reviewed_case_count INTEGER NOT NULL,
            result_json TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(workspace_id, calibration_version),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(dataset_version_id) REFERENCES dataset_versions(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS calibration_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            calibration_run_id INTEGER,
            case_id TEXT NOT NULL,
            reviewer_id INTEGER NOT NULL,
            human_labels TEXT NOT NULL,
            automatic_labels TEXT NOT NULL,
            split TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(workspace_id, case_id, reviewer_id),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
            FOREIGN KEY(calibration_run_id) REFERENCES calibration_runs(id),
            FOREIGN KEY(reviewer_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_calibration_workspace_created
            ON calibration_runs(workspace_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_calibration_reviews_workspace_case
            ON calibration_reviews(workspace_id, case_id);
        """
    )


def _migration_005(conn: sqlite3.Connection) -> None:
    """Record prompt-independent synthetic evidence explicitly."""
    _ensure_column(conn, "eval_results", "synthetic_prompt_ignored", "INTEGER NOT NULL DEFAULT 0")


def _migration_006(conn: sqlite3.Connection) -> None:
    """Add human-readable candidate identity without removing immutable hashes."""
    _ensure_column(conn, "eval_results", "candidate_id", "TEXT")
    _ensure_column(conn, "eval_results", "candidate_name", "TEXT")
    _ensure_column(conn, "eval_results", "target_name", "TEXT")


def _migration_007(conn: sqlite3.Connection) -> None:
    """Add revocable identities and memberships for fail-closed authentication."""
    _ensure_column(conn, "users", "disabled_at", "TEXT")
    _ensure_column(conn, "users", "session_not_before", "TEXT")
    _ensure_column(conn, "memberships", "revoked_at", "TEXT")


def _backfill_legacy_versions(conn: sqlite3.Connection, now: str) -> None:
    for document in conn.execute("SELECT id, workspace_id, filename, content_hash FROM documents").fetchall():
        existing = conn.execute(
            "SELECT id FROM document_versions WHERE document_id = ? LIMIT 1", (document[0],)
        ).fetchone()
        if existing:
            continue
        content_hash = document[3] or f"legacy-document-{document[0]}"
        cursor = conn.execute(
            "INSERT INTO document_versions (workspace_id, document_id, version, content_hash, created_at) VALUES (?, ?, 1, ?, ?)",
            (document[1] or 1, document[0], content_hash, now),
        )
        version_id = _lastrowid(cursor)
        conn.execute(
            "UPDATE chunks SET document_version_id = ? WHERE document_id = ? AND document_version_id IS NULL",
            (version_id, document[0]),
        )
    for prompt in conn.execute("SELECT id, workspace_id, prompt_text FROM prompts").fetchall():
        existing = conn.execute("SELECT id FROM prompt_versions WHERE prompt_id = ? LIMIT 1", (prompt[0],)).fetchone()
        if existing:
            continue
        import hashlib

        content_hash = hashlib.sha256(str(prompt[2] or "").encode("utf-8")).hexdigest()
        cursor = conn.execute(
            "INSERT INTO prompt_versions (workspace_id, prompt_id, version, content, content_hash, created_at) VALUES (?, ?, 1, ?, ?, ?)",
            (prompt[1] or 1, prompt[0], prompt[2] or "", content_hash, now),
        )
        conn.execute("UPDATE prompts SET current_version_id = ? WHERE id = ?", (_lastrowid(cursor), prompt[0]))


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _lastrowid(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite insert did not return a row id.")
    return int(cursor.lastrowid)
