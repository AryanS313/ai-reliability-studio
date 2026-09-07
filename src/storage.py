from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src import config
from src.domain import Role, WorkspaceContext
from src.migrations import migrate_sqlite
from src.security import AuthorizationError, redact_pii, redact_secrets, require_role, sanitize_filename
from src.versioning import text_hash, version_hash


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class Repository(ABC):
    @abstractmethod
    def migrate(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def local_context(self) -> WorkspaceContext:
        raise NotImplementedError

    @abstractmethod
    def authorize(self, context: WorkspaceContext, minimum_role: Role = Role.VIEWER) -> Role:
        raise NotImplementedError

    @abstractmethod
    def audit(
        self,
        context: WorkspaceContext,
        action: str,
        entity_type: str,
        entity_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        raise NotImplementedError


class SQLiteRepository(Repository):
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or config.DATABASE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        with self.connection() as conn:
            migrate_sqlite(conn)

    def local_context(self) -> WorkspaceContext:
        self.migrate()
        with self.connection() as conn:
            user = conn.execute("SELECT id FROM users WHERE email = ?", (config.SINGLE_USER_EMAIL,)).fetchone()
            if user is None:
                user_id = int(
                    conn.execute(
                        "INSERT INTO users (email, display_name, auth_subject, created_at) VALUES (?, ?, ?, ?)",
                        (config.SINGLE_USER_EMAIL, "Local User", f"local:{config.SINGLE_USER_EMAIL}", utcnow()),
                    ).lastrowid
                )
            else:
                user_id = int(user["id"])
            membership = conn.execute(
                """
                SELECT m.workspace_id, m.role FROM memberships m
                JOIN workspaces w ON w.id = m.workspace_id
                WHERE m.user_id = ? AND w.name = ?
                """,
                (user_id, config.SINGLE_USER_WORKSPACE),
            ).fetchone()
            if membership is None:
                workspace_id = int(
                    conn.execute(
                        "INSERT INTO workspaces (name, retention_days, pii_redaction_enabled, created_at) VALUES (?, ?, 0, ?)",
                        (config.SINGLE_USER_WORKSPACE, config.RETENTION_DAYS, utcnow()),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO memberships (user_id, workspace_id, role, created_at) VALUES (?, ?, 'owner', ?)",
                    (user_id, workspace_id, utcnow()),
                )
                role = Role.OWNER
            else:
                workspace_id = int(membership["workspace_id"])
                role = Role(str(membership["role"]))
        return WorkspaceContext(user_id=user_id, workspace_id=workspace_id, role=role)

    def create_workspace(self, owner_email: str, name: str) -> WorkspaceContext:
        self.migrate()
        with self.connection() as conn:
            user = conn.execute("SELECT id FROM users WHERE email = ?", (owner_email.lower(),)).fetchone()
            if user:
                user_id = int(user["id"])
            else:
                user_id = int(
                    conn.execute(
                        "INSERT INTO users (email, display_name, auth_subject, created_at) VALUES (?, ?, ?, ?)",
                        (owner_email.lower(), owner_email.split("@")[0], f"email:{owner_email.lower()}", utcnow()),
                    ).lastrowid
                )
            workspace_id = int(
                conn.execute(
                    "INSERT INTO workspaces (name, retention_days, pii_redaction_enabled, created_at) VALUES (?, ?, 0, ?)",
                    (name, config.RETENTION_DAYS, utcnow()),
                ).lastrowid
            )
            conn.execute(
                "INSERT INTO memberships (user_id, workspace_id, role, created_at) VALUES (?, ?, 'owner', ?)",
                (user_id, workspace_id, utcnow()),
            )
        return WorkspaceContext(user_id=user_id, workspace_id=workspace_id, role=Role.OWNER)

    def add_member(self, context: WorkspaceContext, email: str, role: Role) -> int:
        self.authorize(context, Role.ADMIN)
        if role == Role.OWNER and context.role != Role.OWNER:
            raise AuthorizationError("Only owners may add another owner.")
        with self.connection() as conn:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (email.lower(),)).fetchone()
            if row:
                user_id = int(row["id"])
            else:
                user_id = int(
                    conn.execute(
                        "INSERT INTO users (email, display_name, auth_subject, created_at) VALUES (?, ?, ?, ?)",
                        (email.lower(), email.split("@")[0], f"email:{email.lower()}", utcnow()),
                    ).lastrowid
                )
            conn.execute(
                "INSERT OR REPLACE INTO memberships (user_id, workspace_id, role, created_at) VALUES (?, ?, ?, ?)",
                (user_id, context.workspace_id, role.value, utcnow()),
            )
        self.audit(context, "membership.upsert", "user", str(user_id), {"role": role.value})
        return user_id

    def authorize(self, context: WorkspaceContext, minimum_role: Role = Role.VIEWER) -> Role:
        self.migrate()
        with self.connection() as conn:
            row = conn.execute(
                "SELECT role FROM memberships WHERE user_id = ? AND workspace_id = ? AND revoked_at IS NULL",
                (context.user_id, context.workspace_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("User does not belong to this workspace.")
        actual = Role(str(row["role"]))
        require_role(actual, minimum_role)
        return actual

    def create_project(self, context: WorkspaceContext, metadata: dict[str, str]) -> int:
        self.authorize(context, Role.EDITOR)
        with self.connection() as conn:
            project_id = int(
                conn.execute(
                    """
                    INSERT INTO projects (workspace_id, name, use_case, industry, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        context.workspace_id,
                        metadata.get("name", ""),
                        metadata.get("use_case", ""),
                        metadata.get("industry", ""),
                        metadata.get("notes", ""),
                        utcnow(),
                    ),
                ).lastrowid
            )
        self.audit(context, "project.create", "project", str(project_id), {"name": metadata.get("name", "")})
        return project_id

    def list_projects(self, context: WorkspaceContext) -> list[dict[str, Any]]:
        self.authorize(context)
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE workspace_id = ? ORDER BY id", (context.workspace_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def save_documents_and_chunks(
        self,
        context: WorkspaceContext,
        documents: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        project_id: int | None = None,
    ) -> list[int]:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        version_ids: list[int] = []
        now = utcnow()
        with self.connection() as conn:
            for document in documents:
                original = str(document["filename"])
                safe_name = sanitize_filename(original)
                text = str(document.get("text", ""))
                content_hash = str(document.get("content_hash") or text_hash(text))
                existing = conn.execute(
                    """
                    SELECT id FROM documents
                    WHERE workspace_id = ? AND project_id IS ? AND safe_filename = ?
                    ORDER BY id LIMIT 1
                    """,
                    (context.workspace_id, project_id, safe_name),
                ).fetchone()
                if existing:
                    document_id = int(existing["id"])
                else:
                    document_id = int(
                        conn.execute(
                            """
                            INSERT INTO documents
                            (workspace_id, project_id, filename, safe_filename, content_hash, uploaded_at, chunk_count, status)
                            VALUES (?, ?, ?, ?, ?, ?, 0, 'indexed')
                            """,
                            (context.workspace_id, project_id, original, safe_name, content_hash, now),
                        ).lastrowid
                    )
                version = conn.execute(
                    "SELECT id, version FROM document_versions WHERE document_id = ? AND content_hash = ?",
                    (document_id, content_hash),
                ).fetchone()
                if version:
                    version_id = int(version["id"])
                    version_number = int(version["version"])
                else:
                    next_row = conn.execute(
                        "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM document_versions WHERE document_id = ?",
                        (document_id,),
                    ).fetchone()
                    version_number = int(next_row["version"])
                    version_id = int(
                        conn.execute(
                            """
                            INSERT INTO document_versions
                            (workspace_id, document_id, version, content_hash, extraction_warnings, text_preview, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                context.workspace_id,
                                document_id,
                                version_number,
                                content_hash,
                                json.dumps(document.get("warnings", [])),
                                text[:2000],
                                now,
                            ),
                        ).lastrowid
                    )
                    document_chunks = [item for item in chunks if str(item.get("filename")) == original]
                    for index, chunk in enumerate(document_chunks):
                        chunk_text = str(chunk.get("chunk_text", ""))
                        chunk_id = str(chunk.get("chunk_id") or f"doc-{document_id}-v{version_number}-chunk-{index}")
                        conn.execute(
                            """
                            INSERT INTO chunks
                            (workspace_id, document_id, document_version_id, source_name, filename, chunk_text,
                             chunk_index, chunk_id, page, section, text_start, text_end, content_hash)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                context.workspace_id,
                                document_id,
                                version_id,
                                chunk.get("source_name", safe_name),
                                safe_name,
                                chunk_text,
                                int(chunk.get("chunk_index", index)),
                                chunk_id,
                                chunk.get("page"),
                                chunk.get("section"),
                                chunk.get("text_start"),
                                chunk.get("text_end"),
                                chunk.get("content_hash") or text_hash(chunk_text),
                            ),
                        )
                    conn.execute(
                        "UPDATE documents SET content_hash = ?, uploaded_at = ?, chunk_count = ?, status = 'indexed' WHERE id = ? AND workspace_id = ?",
                        (content_hash, now, len(document_chunks), document_id, context.workspace_id),
                    )
                version_ids.append(version_id)
        self.audit(context, "documents.index", "project", str(project_id or "unassigned"), {"versions": version_ids})
        return version_ids

    def load_chunks(self, context: WorkspaceContext, project_id: int | None = None) -> list[dict[str, Any]]:
        self.authorize(context)
        self._require_project(context, project_id, allow_none=True)
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.document_id, c.document_version_id, c.source_name, c.filename,
                       c.chunk_text, c.chunk_index, c.chunk_id, c.page, c.section, c.text_start,
                       c.text_end, c.content_hash, dv.version AS document_version,
                       dv.content_hash AS document_hash
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                JOIN document_versions dv ON dv.id = c.document_version_id
                WHERE c.workspace_id = ? AND d.project_id IS ?
                  AND dv.version = (SELECT MAX(dv2.version) FROM document_versions dv2 WHERE dv2.document_id = d.id)
                ORDER BY c.id
                """,
                (context.workspace_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_documents(self, context: WorkspaceContext, project_id: int | None = None) -> list[dict[str, Any]]:
        self.authorize(context)
        self._require_project(context, project_id, allow_none=True)
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.filename, d.safe_filename, d.uploaded_at, d.chunk_count, d.status,
                       dv.version, dv.content_hash, dv.extraction_warnings
                FROM documents d
                LEFT JOIN document_versions dv ON dv.document_id = d.id
                    AND dv.version = (SELECT MAX(dv2.version) FROM document_versions dv2 WHERE dv2.document_id = d.id)
                WHERE d.workspace_id = ? AND d.project_id IS ?
                ORDER BY d.id
                """,
                (context.workspace_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_prompt(
        self,
        context: WorkspaceContext,
        project_id: int | None,
        prompt_name: str,
        prompt_text: str,
        prompt_type: str,
        *,
        explanation: str = "",
        motivated_by_failures: list[str] | None = None,
    ) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        digest = text_hash(prompt_text)
        with self.connection() as conn:
            prompt = conn.execute(
                "SELECT id FROM prompts WHERE workspace_id = ? AND project_id IS ? AND prompt_name = ? ORDER BY id LIMIT 1",
                (context.workspace_id, project_id, prompt_name),
            ).fetchone()
            if prompt:
                prompt_id = int(prompt["id"])
            else:
                prompt_id = int(
                    conn.execute(
                        """
                        INSERT INTO prompts
                        (workspace_id, project_id, prompt_name, prompt_text, prompt_type, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (context.workspace_id, project_id, prompt_name, prompt_text, prompt_type, utcnow()),
                    ).lastrowid
                )
            existing = conn.execute(
                "SELECT id FROM prompt_versions WHERE prompt_id = ? AND content_hash = ?",
                (prompt_id, digest),
            ).fetchone()
            if existing:
                version_id = int(existing["id"])
            else:
                next_version = int(
                    conn.execute(
                        "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM prompt_versions WHERE prompt_id = ?",
                        (prompt_id,),
                    ).fetchone()["version"]
                )
                version_id = int(
                    conn.execute(
                        """
                        INSERT INTO prompt_versions
                        (workspace_id, prompt_id, version, content, content_hash, change_explanation,
                         motivated_by_failures, created_by, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            context.workspace_id,
                            prompt_id,
                            next_version,
                            prompt_text,
                            digest,
                            explanation,
                            json.dumps(motivated_by_failures or []),
                            context.user_id,
                            utcnow(),
                        ),
                    ).lastrowid
                )
                conn.execute(
                    "UPDATE prompts SET prompt_text = ?, current_version_id = ? WHERE id = ? AND workspace_id = ?",
                    (prompt_text, version_id, prompt_id, context.workspace_id),
                )
        self.audit(context, "prompt.version.create", "prompt", str(prompt_id), {"version_id": version_id})
        return version_id

    def list_prompts(self, context: WorkspaceContext, project_id: int | None = None) -> list[dict[str, Any]]:
        self.authorize(context)
        self._require_project(context, project_id, allow_none=True)
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT p.*, pv.version, pv.content_hash, pv.change_explanation
                FROM prompts p LEFT JOIN prompt_versions pv ON pv.id = p.current_version_id
                WHERE p.workspace_id = ? AND p.project_id IS ? ORDER BY p.id DESC
                """,
                (context.workspace_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_dataset_version(
        self,
        context: WorkspaceContext,
        project_id: int | None,
        name: str,
        records: list[dict[str, Any]],
        *,
        immutable: bool = False,
    ) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        digest = version_hash(records)
        with self.connection() as conn:
            dataset = conn.execute(
                "SELECT id FROM datasets WHERE workspace_id = ? AND project_id IS ? AND name = ?",
                (context.workspace_id, project_id, name),
            ).fetchone()
            dataset_id = (
                int(dataset["id"])
                if dataset
                else int(
                    conn.execute(
                        "INSERT INTO datasets (workspace_id, project_id, name, created_at) VALUES (?, ?, ?, ?)",
                        (context.workspace_id, project_id, name, utcnow()),
                    ).lastrowid
                )
            )
            existing = conn.execute(
                "SELECT id FROM dataset_versions WHERE dataset_id = ? AND content_hash = ?", (dataset_id, digest)
            ).fetchone()
            if existing:
                return int(existing["id"])
            next_version = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM dataset_versions WHERE dataset_id = ?",
                    (dataset_id,),
                ).fetchone()["version"]
            )
            version_id = int(
                conn.execute(
                    """
                    INSERT INTO dataset_versions
                    (workspace_id, dataset_id, version, content_hash, schema_version, rows_json,
                     case_count, immutable, created_by, created_at)
                    VALUES (?, ?, ?, ?, '1.0', ?, ?, ?, ?, ?)
                    """,
                    (
                        context.workspace_id,
                        dataset_id,
                        next_version,
                        digest,
                        json.dumps(records, default=str),
                        len(records),
                        int(immutable),
                        context.user_id,
                        utcnow(),
                    ),
                ).lastrowid
            )
        self.audit(context, "dataset.version.create", "dataset", str(dataset_id), {"version_id": version_id})
        return version_id

    def create_target_version(
        self,
        context: WorkspaceContext,
        project_id: int | None,
        name: str,
        target_type: str,
        configuration: dict[str, Any],
    ) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        safe_configuration = redact_secrets(configuration)
        if safe_configuration != configuration:
            raise ValueError("Target configuration contains a raw secret; store only secret references.")
        digest = str(configuration.get("version_hash") or version_hash(configuration))
        with self.connection() as conn:
            target = conn.execute(
                "SELECT id FROM targets WHERE workspace_id = ? AND project_id IS ? AND name = ?",
                (context.workspace_id, project_id, name),
            ).fetchone()
            target_id = (
                int(target["id"])
                if target
                else int(
                    conn.execute(
                        "INSERT INTO targets (workspace_id, project_id, name, target_type, created_at) VALUES (?, ?, ?, ?, ?)",
                        (context.workspace_id, project_id, name, target_type, utcnow()),
                    ).lastrowid
                )
            )
            existing = conn.execute(
                "SELECT id FROM target_versions WHERE target_id = ? AND version_hash = ?", (target_id, digest)
            ).fetchone()
            if existing:
                return int(existing["id"])
            next_version = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM target_versions WHERE target_id = ?",
                    (target_id,),
                ).fetchone()["version"]
            )
            version_id = int(
                conn.execute(
                    """
                    INSERT INTO target_versions
                    (workspace_id, target_id, version, version_hash, configuration_json, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        context.workspace_id,
                        target_id,
                        next_version,
                        digest,
                        json.dumps(configuration),
                        context.user_id,
                        utcnow(),
                    ),
                ).lastrowid
            )
        self.audit(context, "target.version.create", "target", str(target_id), {"version_id": version_id})
        return version_id

    def create_run(
        self,
        context: WorkspaceContext,
        *,
        run_name: str,
        model_name: str,
        mode: str,
        unique_case_count: int,
        total_executions: int,
        project_id: int | None = None,
        notes: str = "",
        target_type: str = "synthetic_mock",
        target_version: str | None = None,
        dataset_version_id: int | None = None,
        manifest: dict[str, Any] | None = None,
        evaluator_version: str | None = None,
        label_semantics_version: str | None = None,
        threshold_version: str | None = None,
        calibration_status: str = "insufficiently_calibrated",
        calibration_version: str | None = None,
    ) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        self._require_dataset_version(context, dataset_version_id, project_id)
        with self.connection() as conn:
            run_id = int(
                conn.execute(
                    """
                    INSERT INTO eval_runs
                    (workspace_id, project_id, run_name, timestamp, model_name, mode, total_questions,
                     unique_case_count, total_executions, completed_executions, status, notes, target_type,
                     target_version, dataset_version_id, evaluator_version, label_semantics_version,
                     threshold_version, calibration_status, calibration_version, manifest_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        context.workspace_id,
                        project_id,
                        run_name,
                        utcnow(),
                        model_name,
                        mode,
                        unique_case_count,
                        unique_case_count,
                        total_executions,
                        notes,
                        target_type,
                        target_version,
                        dataset_version_id,
                        evaluator_version,
                        label_semantics_version,
                        threshold_version,
                        calibration_status,
                        calibration_version,
                        json.dumps(manifest or {}),
                    ),
                ).lastrowid
            )
        self.audit(context, "run.create", "run", str(run_id), {"target_type": target_type})
        return run_id

    def save_result(self, context: WorkspaceContext, run_id: int, result: dict[str, Any]) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_run(context, run_id)
        json_fields = {
            "retrieved_sources",
            "retrieved_chunks",
            "citation_details",
            "claim_assessments",
            "failure_labels",
            "failure_reason_codes",
            "failure_evidence",
            "score_explanation",
            "tags",
        }
        allowed = self._table_columns("eval_results") - {"id"}
        payload = {key: value for key, value in result.items() if key in allowed}
        payload.update({"run_id": run_id, "workspace_id": context.workspace_id})
        for field in json_fields:
            if field in payload and not isinstance(payload[field], str):
                payload[field] = json.dumps(payload[field], default=str)
        if "metadata_json" in allowed and "metadata_json" not in payload:
            payload["metadata_json"] = json.dumps(result.get("metadata", {}), default=str)
        columns = list(payload)
        with self.connection() as conn:
            execution_key = version_hash(
                {
                    "run_id": run_id,
                    "case_id": result.get("case_id") or result.get("question"),
                    "prompt_version": result.get("prompt_version"),
                    "target_version": result.get("target_version"),
                }
            )
            prompt_version = conn.execute(
                "SELECT id FROM prompt_versions WHERE workspace_id = ? AND content_hash = ? ORDER BY id DESC LIMIT 1",
                (context.workspace_id, result.get("prompt_version")),
            ).fetchone()
            target_version = conn.execute(
                "SELECT id FROM target_versions WHERE workspace_id = ? AND version_hash = ? ORDER BY id DESC LIMIT 1",
                (context.workspace_id, result.get("target_version")),
            ).fetchone()
            response_payload = {
                key: result.get(key)
                for key in [
                    "actual_answer",
                    "citation_details",
                    "actual_escalation_decision",
                    "escalation_destination",
                    "retrieval_metrics",
                ]
            }
            conn.execute(
                """
                INSERT OR IGNORE INTO executions
                (workspace_id, run_id, case_id, execution_key, prompt_version_id, target_version_id,
                 status, attempt_count, completed_at, latency_ms, http_status, provider, model,
                 input_tokens, output_tokens, cost, error_code, safe_error, response_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context.workspace_id,
                    run_id,
                    str(result.get("case_id") or result.get("question") or "unknown"),
                    execution_key,
                    int(prompt_version["id"]) if prompt_version else None,
                    int(target_version["id"]) if target_version else None,
                    str(result.get("execution_status") or "passed"),
                    utcnow(),
                    result.get("latency_ms"),
                    result.get("http_status"),
                    result.get("provider"),
                    result.get("model_name"),
                    result.get("input_tokens"),
                    result.get("output_tokens"),
                    result.get("estimated_cost"),
                    result.get("error_code"),
                    result.get("safe_error"),
                    json.dumps(response_payload, default=str),
                    json.dumps(redact_secrets(result.get("metadata", {})), default=str),
                ),
            )
            execution = conn.execute(
                "SELECT id FROM executions WHERE workspace_id = ? AND execution_key = ?",
                (context.workspace_id, execution_key),
            ).fetchone()
            execution_id = int(execution["id"])
            if str(result.get("execution_status") or "passed") == "passed":
                metrics = {
                    key: result.get(key)
                    for key in [
                        "expected_answer_match_score",
                        "source_retrieval_score",
                        "citation_correctness_score",
                        "citation_completeness",
                        "groundedness_score",
                        "escalation_correctness_score",
                        "overall_score",
                        "hallucination_risk",
                    ]
                }
                conn.execute(
                    """
                    INSERT INTO scores
                    (workspace_id, execution_id, evaluator_version, determination_state, confidence,
                     metrics_json, explanation_json, failure_labels, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        context.workspace_id,
                        execution_id,
                        result.get("evaluator_version", "deterministic-v3"),
                        result.get("determination_state", "determined"),
                        result.get("evaluator_confidence"),
                        json.dumps(metrics, default=str),
                        json.dumps(result.get("score_explanation", {}), default=str),
                        json.dumps(result.get("failure_labels", []), default=str),
                        utcnow(),
                    ),
                )
                self._persist_sqlite_judge(conn, context, execution_id, result)
            result_id = int(
                conn.execute(
                    f"INSERT INTO eval_results ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",  # noqa: S608 - columns are intersected with PRAGMA-derived schema names
                    [payload[column] for column in columns],
                ).lastrowid
            )
            conn.execute(
                """
                UPDATE eval_runs
                SET completed_executions = completed_executions + 1,
                    status = CASE WHEN completed_executions + 1 >= total_executions THEN 'completed' ELSE 'running' END
                WHERE id = ? AND workspace_id = ?
                """,
                (run_id, context.workspace_id),
            )
        return result_id

    def list_results(self, context: WorkspaceContext, run_id: int | None = None) -> list[dict[str, Any]]:
        self.authorize(context)
        if run_id is not None:
            self._require_run(context, run_id)
        with self.connection() as conn:
            if run_id is None:
                rows = conn.execute(
                    """
                    SELECT er.*, runs.run_name, runs.timestamp, runs.mode, runs.status AS run_status
                    FROM eval_results er JOIN eval_runs runs ON runs.id = er.run_id
                    WHERE er.workspace_id = ? ORDER BY er.id DESC
                    """,
                    (context.workspace_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT er.*, runs.run_name, runs.timestamp, runs.mode, runs.status AS run_status
                    FROM eval_results er JOIN eval_runs runs ON runs.id = er.run_id
                    WHERE er.workspace_id = ? AND er.run_id = ? ORDER BY er.id DESC
                    """,
                    (context.workspace_id, run_id),
                ).fetchall()
        return [dict(row) for row in rows]

    def latest_results(self, context: WorkspaceContext) -> list[dict[str, Any]]:
        self.authorize(context)
        with self.connection() as conn:
            run = conn.execute(
                "SELECT id FROM eval_runs WHERE workspace_id = ? ORDER BY timestamp DESC, id DESC LIMIT 1",
                (context.workspace_id,),
            ).fetchone()
        return self.list_results(context, int(run["id"])) if run else []

    def list_runs(self, context: WorkspaceContext) -> list[dict[str, Any]]:
        self.authorize(context)
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM eval_runs WHERE workspace_id = ? ORDER BY id DESC", (context.workspace_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def request_run_cancellation(self, context: WorkspaceContext, run_id: int) -> None:
        self.authorize(context, Role.EDITOR)
        self._require_run(context, run_id)
        with self.connection() as conn:
            conn.execute(
                "UPDATE eval_runs SET cancel_requested = 1 WHERE id = ? AND workspace_id = ?",
                (run_id, context.workspace_id),
            )
        self.audit(context, "run.cancel.request", "run", str(run_id), {})

    def record_export(
        self,
        context: WorkspaceContext,
        report_format: str,
        content_hash: str,
        run_id: int | None = None,
    ) -> int:
        self.authorize(context, Role.VIEWER)
        if report_format not in {"csv", "json", "html"}:
            raise ValueError("Unsupported export format.")
        if run_id is not None:
            self._require_run(context, run_id)
        with self.connection() as conn:
            export_id = int(
                conn.execute(
                    """
                    INSERT INTO exports (workspace_id, user_id, run_id, format, content_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (context.workspace_id, context.user_id, run_id, report_format, content_hash, utcnow()),
                ).lastrowid
            )
        self.audit(
            context, "report.export", "run", str(run_id) if run_id is not None else None, {"format": report_format}
        )
        return export_id

    def save_calibration_reviews(self, context: WorkspaceContext, records: list[dict[str, Any]]) -> int:
        self.authorize(context, Role.REVIEWER)
        with self.connection() as conn:
            for record in records:
                conn.execute(
                    """
                    INSERT INTO calibration_reviews
                    (workspace_id, case_id, reviewer_id, human_labels, automatic_labels, split, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(workspace_id, case_id, reviewer_id) DO UPDATE SET
                        human_labels = excluded.human_labels,
                        automatic_labels = excluded.automatic_labels,
                        split = excluded.split,
                        notes = excluded.notes,
                        created_at = excluded.created_at
                    """,
                    (
                        context.workspace_id,
                        str(record["case_id"]),
                        context.user_id,
                        json.dumps(record.get("human_labels", [])),
                        json.dumps(record.get("automatic_labels", [])),
                        str(record.get("split") or "holdout"),
                        redact_pii(str(redact_secrets(record.get("notes", "")))),
                        utcnow(),
                    ),
                )
        self.audit(
            context, "calibration.review.upsert", "workspace", str(context.workspace_id), {"count": len(records)}
        )
        return len(records)

    def save_calibration_result(
        self,
        context: WorkspaceContext,
        result: dict[str, Any],
        *,
        evaluator_version: str,
        dataset_version_id: int | None = None,
    ) -> int:
        self.authorize(context, Role.REVIEWER)
        if dataset_version_id is not None:
            with self.connection() as conn:
                row = conn.execute(
                    "SELECT id FROM dataset_versions WHERE id = ? AND workspace_id = ?",
                    (dataset_version_id, context.workspace_id),
                ).fetchone()
            if row is None:
                raise AuthorizationError("Calibration dataset version does not belong to this workspace.")
        calibration_version = str(result["calibration_version"])
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO calibration_runs
                (workspace_id, dataset_version_id, evaluator_version, threshold_version,
                 calibration_version, status, reviewed_case_count, result_json, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context.workspace_id,
                    dataset_version_id,
                    evaluator_version,
                    result["threshold_version"],
                    calibration_version,
                    result["status"],
                    int(result.get("reviewed_cases", 0)),
                    json.dumps(redact_secrets(result), default=str),
                    context.user_id,
                    utcnow(),
                ),
            )
            row = conn.execute(
                "SELECT id FROM calibration_runs WHERE workspace_id = ? AND calibration_version = ?",
                (context.workspace_id, calibration_version),
            ).fetchone()
            calibration_id = int(row["id"])
        self.audit(
            context, "calibration.run.create", "calibration_run", str(calibration_id), {"status": result["status"]}
        )
        return calibration_id

    def latest_calibration(
        self,
        context: WorkspaceContext,
        *,
        threshold_version: str | None = None,
    ) -> dict[str, Any] | None:
        self.authorize(context, Role.VIEWER)
        query = "SELECT * FROM calibration_runs WHERE workspace_id = ?"
        parameters: list[Any] = [context.workspace_id]
        if threshold_version:
            query += " AND threshold_version = ?"
            parameters.append(threshold_version)
        query += " ORDER BY created_at DESC, id DESC LIMIT 1"
        with self.connection() as conn:
            row = conn.execute(query, parameters).fetchone()
        if row is None:
            return None
        output = dict(row)
        output["result"] = json.loads(output.pop("result_json"))
        return output

    def clear_results(self, context: WorkspaceContext) -> None:
        self.authorize(context, Role.ADMIN)
        with self.connection() as conn:
            run_ids = [
                int(row["id"])
                for row in conn.execute("SELECT id FROM eval_runs WHERE workspace_id = ?", (context.workspace_id,))
            ]
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                execution_ids = [
                    int(row["id"])
                    for row in conn.execute(
                        f"SELECT id FROM executions WHERE workspace_id = ? AND run_id IN ({placeholders})",  # noqa: S608 - placeholders contain only '?' generated from integer ids
                        [context.workspace_id, *run_ids],
                    )
                ]
                if execution_ids:
                    execution_placeholders = ",".join("?" for _ in execution_ids)
                    for table in ["comments", "review_assignments", "judgments", "scores"]:
                        conn.execute(
                            f"DELETE FROM {table} WHERE workspace_id = ? AND execution_id IN ({execution_placeholders})",  # noqa: S608 - table is selected from a fixed allowlist
                            [context.workspace_id, *execution_ids],
                        )
                conn.execute("UPDATE exports SET run_id = NULL WHERE workspace_id = ?", (context.workspace_id,))
                conn.execute("DELETE FROM eval_results WHERE workspace_id = ?", (context.workspace_id,))
                conn.execute("DELETE FROM executions WHERE workspace_id = ?", (context.workspace_id,))
                conn.execute("DELETE FROM eval_runs WHERE workspace_id = ?", (context.workspace_id,))
        self.audit(context, "results.clear", "workspace", str(context.workspace_id), {})

    def reset_workspace(self, context: WorkspaceContext) -> None:
        """Explicit workspace-only reset. It never drops tables or touches another workspace."""
        self.authorize(context, Role.OWNER)
        self.clear_results(context)
        with self.connection() as conn:
            document_ids = [
                int(row["id"])
                for row in conn.execute("SELECT id FROM documents WHERE workspace_id = ?", (context.workspace_id,))
            ]
            prompt_ids = [
                int(row["id"])
                for row in conn.execute("SELECT id FROM prompts WHERE workspace_id = ?", (context.workspace_id,))
            ]
            dataset_ids = [
                int(row["id"])
                for row in conn.execute("SELECT id FROM datasets WHERE workspace_id = ?", (context.workspace_id,))
            ]
            target_ids = [
                int(row["id"])
                for row in conn.execute("SELECT id FROM targets WHERE workspace_id = ?", (context.workspace_id,))
            ]
            conn.execute("DELETE FROM chunks WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM document_versions WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM documents WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM prompt_versions WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM prompts WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM dataset_versions WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM datasets WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM target_versions WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM targets WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM scheduled_evaluations WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM execution_cache WHERE workspace_id = ?", (context.workspace_id,))
            conn.execute("DELETE FROM projects WHERE workspace_id = ?", (context.workspace_id,))
        self.audit(
            context,
            "workspace.reset",
            "workspace",
            str(context.workspace_id),
            {
                "documents": len(document_ids),
                "prompts": len(prompt_ids),
                "datasets": len(dataset_ids),
                "targets": len(target_ids),
            },
        )

    def audit(
        self,
        context: WorkspaceContext,
        action: str,
        entity_type: str,
        entity_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        self.authorize(context, Role.VIEWER)
        safe = redact_secrets(metadata, preserve_references=False)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs
                (workspace_id, user_id, action, entity_type, entity_id, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (context.workspace_id, context.user_id, action, entity_type, entity_id, json.dumps(safe), utcnow()),
            )

    def purge_expired_data(self, context: WorkspaceContext) -> int:
        self.authorize(context, Role.OWNER)
        with self.connection() as conn:
            workspace = conn.execute(
                "SELECT retention_days FROM workspaces WHERE id = ?", (context.workspace_id,)
            ).fetchone()
            cutoff = datetime.now(UTC) - timedelta(days=int(workspace["retention_days"]))
            rows = conn.execute(
                "SELECT id FROM eval_runs WHERE workspace_id = ? AND timestamp < ?",
                (context.workspace_id, cutoff.isoformat()),
            ).fetchall()
            run_ids = [int(row["id"]) for row in rows]
            for run_id in run_ids:
                execution_ids = [
                    int(row["id"])
                    for row in conn.execute(
                        "SELECT id FROM executions WHERE workspace_id = ? AND run_id = ?",
                        (context.workspace_id, run_id),
                    )
                ]
                if execution_ids:
                    placeholders = ",".join("?" for _ in execution_ids)
                    for table in ["comments", "review_assignments", "judgments", "scores"]:
                        conn.execute(
                            f"DELETE FROM {table} WHERE workspace_id = ? AND execution_id IN ({placeholders})",  # noqa: S608 - fixed allowlist and generated placeholders
                            [context.workspace_id, *execution_ids],
                        )
                conn.execute(
                    "UPDATE exports SET run_id = NULL WHERE workspace_id = ? AND run_id = ?",
                    (context.workspace_id, run_id),
                )
                conn.execute(
                    "DELETE FROM eval_results WHERE workspace_id = ? AND run_id = ?", (context.workspace_id, run_id)
                )
                conn.execute(
                    "DELETE FROM executions WHERE workspace_id = ? AND run_id = ?", (context.workspace_id, run_id)
                )
                conn.execute("DELETE FROM eval_runs WHERE workspace_id = ? AND id = ?", (context.workspace_id, run_id))
        self.audit(context, "retention.purge", "workspace", str(context.workspace_id), {"runs": len(run_ids)})
        return len(run_ids)

    def _require_project(self, context: WorkspaceContext, project_id: int | None, *, allow_none: bool) -> None:
        if project_id is None and allow_none:
            return
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id FROM projects WHERE id = ? AND workspace_id = ?", (project_id, context.workspace_id)
            ).fetchone()
        if row is None:
            raise AuthorizationError("Project does not belong to the active workspace.")

    def _require_run(self, context: WorkspaceContext, run_id: int) -> None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id FROM eval_runs WHERE id = ? AND workspace_id = ?", (run_id, context.workspace_id)
            ).fetchone()
        if row is None:
            raise AuthorizationError("Run does not belong to the active workspace.")

    def _require_dataset_version(
        self,
        context: WorkspaceContext,
        dataset_version_id: int | None,
        project_id: int | None,
    ) -> None:
        if dataset_version_id is None:
            return
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT dv.id FROM dataset_versions dv JOIN datasets d ON d.id = dv.dataset_id
                WHERE dv.id = ? AND dv.workspace_id = ? AND d.workspace_id = ? AND d.project_id IS ?
                """,
                (dataset_version_id, context.workspace_id, context.workspace_id, project_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("Dataset version does not belong to this workspace and project.")

    def _table_columns(self, table: str) -> set[str]:
        with self.connection() as conn:
            return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _persist_sqlite_judge(
        conn: sqlite3.Connection,
        context: WorkspaceContext,
        execution_id: int,
        result: dict[str, Any],
    ) -> None:
        judge = dict(result.get("score_explanation", {}).get("judge") or {})
        if not judge:
            return
        settings = dict(judge.get("configuration") or {})
        conn.execute(
            """
            INSERT INTO judgments
            (workspace_id, execution_id, evaluator_type, provider, model, prompt, prompt_hash,
             temperature, output_json, confidence, created_at)
            VALUES (?, ?, 'llm_judge', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context.workspace_id,
                execution_id,
                settings.get("provider"),
                settings.get("model"),
                settings.get("prompt_template"),
                settings.get("prompt_hash"),
                settings.get("temperature"),
                json.dumps(judge, default=str),
                judge.get("confidence"),
                utcnow(),
            ),
        )


class PostgresRepository(Repository):
    """Production PostgreSQL connection and migration boundary.

    The PostgreSQL schema is applied from `migrations/postgres.sql`. Application
    services use workspace-scoped queries; deployments should also enable the RLS
    policies included in that migration.
    """

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("PostgresRepository requires a PostgreSQL URL")
        self.database_url = database_url

    @contextmanager
    def connection(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on production extra
            raise RuntimeError("Install psycopg[binary] to use PostgreSQL production storage.") from exc
        conn = psycopg.connect(self.database_url, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        migration = Path(__file__).resolve().parents[1] / "migrations" / "postgres.sql"
        with self.connection() as conn:
            conn.execute(migration.read_text(encoding="utf-8"))

    def local_context(self) -> WorkspaceContext:
        if config.AUTH_MODE == "single-user" and config.APP_ENV == "production":
            raise RuntimeError("Production PostgreSQL requires authenticated mode; single-user mode is refused.")
        if config.AUTH_MODE != "single-user":
            raise RuntimeError(
                "Resolve an authenticated identity with src.auth before creating a PostgreSQL workspace context."
            )
        return self._bootstrap_context(config.SINGLE_USER_EMAIL, config.SINGLE_USER_WORKSPACE)

    def authorize(self, context: WorkspaceContext, minimum_role: Role = Role.VIEWER) -> Role:
        with self.connection() as conn:
            self._scope(conn, context)
            row = conn.execute(
                "SELECT role FROM memberships WHERE user_id = %s AND workspace_id = %s AND revoked_at IS NULL",
                (context.user_id, context.workspace_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("User does not belong to this workspace.")
        role = Role(str(row["role"]))
        require_role(role, minimum_role)
        return role

    def create_workspace(self, owner_email: str, name: str) -> WorkspaceContext:
        return self._bootstrap_context(owner_email, name, always_create_workspace=True)

    def add_member(self, context: WorkspaceContext, email: str, role: Role) -> int:
        self.authorize(context, Role.ADMIN)
        with self.connection() as conn:
            self._scope(conn, context)
            user = conn.execute(
                """
                INSERT INTO users (email, display_name, auth_subject)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
                RETURNING id
                """,
                (email.lower(), email.split("@")[0], f"email:{email.lower()}"),
            ).fetchone()
            user_id = int(user["id"])
            conn.execute(
                """
                INSERT INTO memberships (user_id, workspace_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, workspace_id) DO UPDATE SET role = EXCLUDED.role, revoked_at = NULL
                """,
                (user_id, context.workspace_id, role.value),
            )
        self.audit(context, "membership.upsert", "user", str(user_id), {"role": role.value})
        return user_id

    def create_project(self, context: WorkspaceContext, metadata: dict[str, str]) -> int:
        self.authorize(context, Role.EDITOR)
        with self.connection() as conn:
            self._scope(conn, context)
            row = conn.execute(
                """
                INSERT INTO projects (workspace_id, name, use_case, industry, notes)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    context.workspace_id,
                    metadata.get("name", ""),
                    metadata.get("use_case", ""),
                    metadata.get("industry", ""),
                    metadata.get("notes", ""),
                ),
            ).fetchone()
        project_id = int(row["id"])
        self.audit(context, "project.create", "project", str(project_id), {"name": metadata.get("name", "")})
        return project_id

    def list_projects(self, context: WorkspaceContext) -> list[dict[str, Any]]:
        self.authorize(context)
        with self.connection() as conn:
            self._scope(conn, context)
            rows = conn.execute(
                "SELECT * FROM projects WHERE workspace_id = %s ORDER BY id", (context.workspace_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def save_documents_and_chunks(
        self,
        context: WorkspaceContext,
        documents: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        project_id: int | None = None,
    ) -> list[int]:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        version_ids: list[int] = []
        with self.connection() as conn:
            self._scope(conn, context)
            for document in documents:
                original = str(document["filename"])
                safe_name = sanitize_filename(original)
                text = str(document.get("text", ""))
                digest = str(document.get("content_hash") or text_hash(text))
                row = conn.execute(
                    """
                    SELECT id FROM documents WHERE workspace_id = %s
                    AND project_id IS NOT DISTINCT FROM %s AND safe_filename = %s ORDER BY id LIMIT 1
                    """,
                    (context.workspace_id, project_id, safe_name),
                ).fetchone()
                if row:
                    document_id = int(row["id"])
                else:
                    row = conn.execute(
                        """
                        INSERT INTO documents
                        (workspace_id, project_id, filename, safe_filename, content_hash, chunk_count, status)
                        VALUES (%s, %s, %s, %s, %s, 0, 'indexed') RETURNING id
                        """,
                        (context.workspace_id, project_id, original, safe_name, digest),
                    ).fetchone()
                    document_id = int(row["id"])
                version = conn.execute(
                    "SELECT id, version FROM document_versions WHERE document_id = %s AND content_hash = %s",
                    (document_id, digest),
                ).fetchone()
                if version:
                    version_id = int(version["id"])
                else:
                    next_version = int(
                        conn.execute(
                            "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM document_versions WHERE document_id = %s",
                            (document_id,),
                        ).fetchone()["version"]
                    )
                    version = conn.execute(
                        """
                        INSERT INTO document_versions
                        (workspace_id, document_id, version, content_hash, extraction_warnings, text_preview)
                        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                        """,
                        (
                            context.workspace_id,
                            document_id,
                            next_version,
                            digest,
                            json.dumps(document.get("warnings", [])),
                            text[:2000],
                        ),
                    ).fetchone()
                    version_id = int(version["id"])
                    document_chunks = [item for item in chunks if str(item.get("filename")) == original]
                    for index, chunk in enumerate(document_chunks):
                        chunk_text = str(chunk.get("chunk_text", ""))
                        conn.execute(
                            """
                            INSERT INTO chunks
                            (workspace_id, document_id, document_version_id, source_name, filename, chunk_text,
                             chunk_index, chunk_id, page, section, text_start, text_end, content_hash)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                context.workspace_id,
                                document_id,
                                version_id,
                                chunk.get("source_name", safe_name),
                                safe_name,
                                chunk_text,
                                int(chunk.get("chunk_index", index)),
                                str(chunk.get("chunk_id") or f"doc-{document_id}-v{next_version}-chunk-{index}"),
                                chunk.get("page"),
                                chunk.get("section"),
                                chunk.get("text_start"),
                                chunk.get("text_end"),
                                chunk.get("content_hash") or text_hash(chunk_text),
                            ),
                        )
                    conn.execute(
                        "UPDATE documents SET content_hash = %s, uploaded_at = now(), chunk_count = %s WHERE id = %s AND workspace_id = %s",
                        (digest, len(document_chunks), document_id, context.workspace_id),
                    )
                version_ids.append(version_id)
        self.audit(context, "documents.index", "project", str(project_id or "unassigned"), {"versions": version_ids})
        return version_ids

    def load_chunks(self, context: WorkspaceContext, project_id: int | None = None) -> list[dict[str, Any]]:
        self.authorize(context)
        self._require_project(context, project_id, allow_none=True)
        with self.connection() as conn:
            self._scope(conn, context)
            rows = conn.execute(
                """
                SELECT c.*, dv.version AS document_version, dv.content_hash AS document_hash
                FROM chunks c JOIN documents d ON d.id = c.document_id
                JOIN document_versions dv ON dv.id = c.document_version_id
                WHERE c.workspace_id = %s AND d.project_id IS NOT DISTINCT FROM %s
                  AND dv.version = (SELECT MAX(dv2.version) FROM document_versions dv2 WHERE dv2.document_id = d.id)
                ORDER BY c.id
                """,
                (context.workspace_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_documents(self, context: WorkspaceContext, project_id: int | None = None) -> list[dict[str, Any]]:
        self.authorize(context)
        self._require_project(context, project_id, allow_none=True)
        with self.connection() as conn:
            self._scope(conn, context)
            rows = conn.execute(
                """
                SELECT d.id, d.filename, d.safe_filename, d.uploaded_at, d.chunk_count, d.status,
                       dv.version, dv.content_hash, dv.extraction_warnings
                FROM documents d LEFT JOIN document_versions dv ON dv.document_id = d.id
                 AND dv.version = (SELECT MAX(dv2.version) FROM document_versions dv2 WHERE dv2.document_id = d.id)
                WHERE d.workspace_id = %s AND d.project_id IS NOT DISTINCT FROM %s ORDER BY d.id
                """,
                (context.workspace_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_prompt(
        self,
        context: WorkspaceContext,
        project_id: int | None,
        prompt_name: str,
        prompt_text: str,
        prompt_type: str,
        *,
        explanation: str = "",
        motivated_by_failures: list[str] | None = None,
    ) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        digest = text_hash(prompt_text)
        with self.connection() as conn:
            self._scope(conn, context)
            prompt = conn.execute(
                """
                SELECT id FROM prompts WHERE workspace_id = %s
                AND project_id IS NOT DISTINCT FROM %s AND prompt_name = %s ORDER BY id LIMIT 1
                """,
                (context.workspace_id, project_id, prompt_name),
            ).fetchone()
            if prompt:
                prompt_id = int(prompt["id"])
            else:
                prompt = conn.execute(
                    """
                    INSERT INTO prompts (workspace_id, project_id, prompt_name, prompt_text, prompt_type)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                    """,
                    (context.workspace_id, project_id, prompt_name, prompt_text, prompt_type),
                ).fetchone()
                prompt_id = int(prompt["id"])
            existing = conn.execute(
                "SELECT id FROM prompt_versions WHERE prompt_id = %s AND content_hash = %s",
                (prompt_id, digest),
            ).fetchone()
            if existing:
                version_id = int(existing["id"])
            else:
                next_version = int(
                    conn.execute(
                        "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM prompt_versions WHERE prompt_id = %s",
                        (prompt_id,),
                    ).fetchone()["version"]
                )
                version = conn.execute(
                    """
                    INSERT INTO prompt_versions
                    (workspace_id, prompt_id, version, content, content_hash, change_explanation,
                     motivated_by_failures, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """,
                    (
                        context.workspace_id,
                        prompt_id,
                        next_version,
                        prompt_text,
                        digest,
                        explanation,
                        json.dumps(motivated_by_failures or []),
                        context.user_id,
                    ),
                ).fetchone()
                version_id = int(version["id"])
                conn.execute(
                    "UPDATE prompts SET prompt_text = %s, current_version_id = %s WHERE id = %s AND workspace_id = %s",
                    (prompt_text, version_id, prompt_id, context.workspace_id),
                )
        self.audit(context, "prompt.version.create", "prompt", str(prompt_id), {"version_id": version_id})
        return version_id

    def list_prompts(self, context: WorkspaceContext, project_id: int | None = None) -> list[dict[str, Any]]:
        self.authorize(context)
        self._require_project(context, project_id, allow_none=True)
        with self.connection() as conn:
            self._scope(conn, context)
            rows = conn.execute(
                """
                SELECT p.*, pv.version, pv.content_hash, pv.change_explanation
                FROM prompts p LEFT JOIN prompt_versions pv ON pv.id = p.current_version_id
                WHERE p.workspace_id = %s AND p.project_id IS NOT DISTINCT FROM %s ORDER BY p.id DESC
                """,
                (context.workspace_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_dataset_version(
        self,
        context: WorkspaceContext,
        project_id: int | None,
        name: str,
        records: list[dict[str, Any]],
        *,
        immutable: bool = False,
    ) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        digest = version_hash(records)
        with self.connection() as conn:
            self._scope(conn, context)
            dataset = conn.execute(
                """
                SELECT id FROM datasets WHERE workspace_id = %s
                 AND project_id IS NOT DISTINCT FROM %s AND name = %s
                """,
                (context.workspace_id, project_id, name),
            ).fetchone()
            if not dataset:
                dataset = conn.execute(
                    "INSERT INTO datasets (workspace_id, project_id, name) VALUES (%s, %s, %s) RETURNING id",
                    (context.workspace_id, project_id, name),
                ).fetchone()
            dataset_id = int(dataset["id"])
            existing = conn.execute(
                "SELECT id FROM dataset_versions WHERE dataset_id = %s AND content_hash = %s",
                (dataset_id, digest),
            ).fetchone()
            if existing:
                return int(existing["id"])
            next_version = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM dataset_versions WHERE dataset_id = %s",
                    (dataset_id,),
                ).fetchone()["version"]
            )
            version = conn.execute(
                """
                INSERT INTO dataset_versions
                (workspace_id, dataset_id, version, content_hash, schema_version, rows_json,
                 case_count, immutable, created_by)
                VALUES (%s, %s, %s, %s, '1.0', %s, %s, %s, %s) RETURNING id
                """,
                (
                    context.workspace_id,
                    dataset_id,
                    next_version,
                    digest,
                    json.dumps(records, default=str),
                    len(records),
                    immutable,
                    context.user_id,
                ),
            ).fetchone()
        version_id = int(version["id"])
        self.audit(context, "dataset.version.create", "dataset", str(dataset_id), {"version_id": version_id})
        return version_id

    def create_target_version(
        self,
        context: WorkspaceContext,
        project_id: int | None,
        name: str,
        target_type: str,
        configuration: dict[str, Any],
    ) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        if redact_secrets(configuration) != configuration:
            raise ValueError("Target configuration contains a raw secret; store only secret references.")
        digest = str(configuration.get("version_hash") or version_hash(configuration))
        with self.connection() as conn:
            self._scope(conn, context)
            target = conn.execute(
                """
                SELECT id FROM targets WHERE workspace_id = %s
                 AND project_id IS NOT DISTINCT FROM %s AND name = %s
                """,
                (context.workspace_id, project_id, name),
            ).fetchone()
            if not target:
                target = conn.execute(
                    """
                    INSERT INTO targets (workspace_id, project_id, name, target_type)
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (context.workspace_id, project_id, name, target_type),
                ).fetchone()
            target_id = int(target["id"])
            existing = conn.execute(
                "SELECT id FROM target_versions WHERE target_id = %s AND version_hash = %s",
                (target_id, digest),
            ).fetchone()
            if existing:
                return int(existing["id"])
            next_version = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM target_versions WHERE target_id = %s",
                    (target_id,),
                ).fetchone()["version"]
            )
            version = conn.execute(
                """
                INSERT INTO target_versions
                (workspace_id, target_id, version, version_hash, configuration_json, created_by)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    context.workspace_id,
                    target_id,
                    next_version,
                    digest,
                    json.dumps(configuration),
                    context.user_id,
                ),
            ).fetchone()
        version_id = int(version["id"])
        self.audit(context, "target.version.create", "target", str(target_id), {"version_id": version_id})
        return version_id

    def create_run(
        self,
        context: WorkspaceContext,
        *,
        run_name: str,
        model_name: str,
        mode: str,
        unique_case_count: int,
        total_executions: int,
        project_id: int | None = None,
        notes: str = "",
        target_type: str = "synthetic_mock",
        target_version: str | None = None,
        dataset_version_id: int | None = None,
        manifest: dict[str, Any] | None = None,
        evaluator_version: str | None = None,
        label_semantics_version: str | None = None,
        threshold_version: str | None = None,
        calibration_status: str = "insufficiently_calibrated",
        calibration_version: str | None = None,
    ) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_project(context, project_id, allow_none=True)
        self._require_dataset_version(context, dataset_version_id, project_id)
        with self.connection() as conn:
            self._scope(conn, context)
            run = conn.execute(
                """
                INSERT INTO eval_runs
                (workspace_id, project_id, run_name, model_name, mode, status, target_type,
                 target_version, dataset_version_id, unique_case_count, total_executions,
                 completed_executions, evaluator_version, label_semantics_version, threshold_version,
                 calibration_status, calibration_version, manifest_json, notes)
                VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    context.workspace_id,
                    project_id,
                    run_name,
                    model_name,
                    mode,
                    target_type,
                    target_version,
                    dataset_version_id,
                    unique_case_count,
                    total_executions,
                    evaluator_version,
                    label_semantics_version,
                    threshold_version,
                    calibration_status,
                    calibration_version,
                    json.dumps(manifest or {}),
                    notes,
                ),
            ).fetchone()
        run_id = int(run["id"])
        self.audit(context, "run.create", "run", str(run_id), {"target_type": target_type})
        return run_id

    def save_result(self, context: WorkspaceContext, run_id: int, result: dict[str, Any]) -> int:
        self.authorize(context, Role.EDITOR)
        self._require_run(context, run_id)
        execution_key = version_hash(
            {
                "run_id": run_id,
                "case_id": result.get("case_id") or result.get("question"),
                "prompt_version": result.get("prompt_version"),
                "target_version": result.get("target_version"),
            }
        )
        with self.connection() as conn:
            self._scope(conn, context)
            execution = conn.execute(
                """
                INSERT INTO executions
                (workspace_id, run_id, case_id, execution_key, status, attempt_count, completed_at,
                 latency_ms, http_status, provider, model, input_tokens, output_tokens, cost,
                 error_code, safe_error, response_json, metadata_json)
                VALUES (%s, %s, %s, %s, %s, 1, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id, execution_key) DO UPDATE SET status = EXCLUDED.status
                RETURNING id
                """,
                (
                    context.workspace_id,
                    run_id,
                    str(result.get("case_id") or result.get("question") or "unknown"),
                    execution_key,
                    str(result.get("execution_status") or "passed"),
                    result.get("latency_ms"),
                    result.get("http_status"),
                    result.get("provider"),
                    result.get("model_name"),
                    result.get("input_tokens"),
                    result.get("output_tokens"),
                    result.get("estimated_cost"),
                    result.get("error_code"),
                    result.get("safe_error"),
                    json.dumps({"answer": result.get("actual_answer")}, default=str),
                    json.dumps(redact_secrets(result.get("metadata", {})), default=str),
                ),
            ).fetchone()
            execution_id = int(execution["id"])
            if str(result.get("execution_status") or "passed") == "passed":
                conn.execute(
                    """
                    INSERT INTO scores
                    (workspace_id, execution_id, evaluator_version, determination_state, confidence,
                     metrics_json, explanation_json, failure_labels)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        context.workspace_id,
                        execution_id,
                        result.get("evaluator_version", "deterministic-v3"),
                        result.get("determination_state", "determined"),
                        result.get("evaluator_confidence"),
                        json.dumps({"overall_score": result.get("overall_score")}),
                        json.dumps(result.get("score_explanation", {}), default=str),
                        json.dumps(result.get("failure_labels", []), default=str),
                    ),
                )
                self._persist_postgres_judge(conn, context, execution_id, result)
            saved = conn.execute(
                """
                INSERT INTO eval_results
                (workspace_id, run_id, evaluator_version, label_semantics_version, threshold_version,
                 calibration_status, calibration_version, failure_reason_codes, failure_evidence, result_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    context.workspace_id,
                    run_id,
                    result.get("evaluator_version"),
                    result.get("label_semantics_version"),
                    result.get("threshold_version"),
                    result.get("calibration_status", "insufficiently_calibrated"),
                    result.get("calibration_version"),
                    json.dumps(result.get("failure_reason_codes", []), default=str),
                    json.dumps(result.get("failure_evidence", {}), default=str),
                    json.dumps(result, default=str),
                ),
            ).fetchone()
            conn.execute(
                """
                UPDATE eval_runs SET completed_executions = completed_executions + 1,
                 status = CASE WHEN completed_executions + 1 >= total_executions THEN 'completed' ELSE 'running' END
                WHERE id = %s AND workspace_id = %s
                """,
                (run_id, context.workspace_id),
            )
        return int(saved["id"])

    def list_results(self, context: WorkspaceContext, run_id: int | None = None) -> list[dict[str, Any]]:
        self.authorize(context)
        if run_id is not None:
            self._require_run(context, run_id)
        with self.connection() as conn:
            self._scope(conn, context)
            if run_id is None:
                rows = conn.execute(
                    """
                    SELECT er.result_json, r.run_name, r.timestamp, r.mode, r.status AS run_status
                    FROM eval_results er JOIN eval_runs r ON r.id = er.run_id
                    WHERE er.workspace_id = %s ORDER BY er.id DESC
                    """,
                    (context.workspace_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT er.result_json, r.run_name, r.timestamp, r.mode, r.status AS run_status
                    FROM eval_results er JOIN eval_runs r ON r.id = er.run_id
                    WHERE er.workspace_id = %s AND er.run_id = %s ORDER BY er.id DESC
                    """,
                    (context.workspace_id, run_id),
                ).fetchall()
        output = []
        for row in rows:
            result = row["result_json"] if isinstance(row["result_json"], dict) else json.loads(row["result_json"])
            result.update({key: row[key] for key in ["run_name", "timestamp", "mode", "run_status"]})
            output.append(result)
        return output

    def latest_results(self, context: WorkspaceContext) -> list[dict[str, Any]]:
        runs = self.list_runs(context)
        return self.list_results(context, int(runs[0]["id"])) if runs else []

    def list_runs(self, context: WorkspaceContext) -> list[dict[str, Any]]:
        self.authorize(context)
        with self.connection() as conn:
            self._scope(conn, context)
            rows = conn.execute(
                "SELECT * FROM eval_runs WHERE workspace_id = %s ORDER BY id DESC", (context.workspace_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def request_run_cancellation(self, context: WorkspaceContext, run_id: int) -> None:
        self.authorize(context, Role.EDITOR)
        self._require_run(context, run_id)
        with self.connection() as conn:
            self._scope(conn, context)
            conn.execute(
                "UPDATE eval_runs SET cancel_requested = true WHERE id = %s AND workspace_id = %s",
                (run_id, context.workspace_id),
            )
        self.audit(context, "run.cancel.request", "run", str(run_id), {})

    def record_export(
        self,
        context: WorkspaceContext,
        report_format: str,
        content_hash: str,
        run_id: int | None = None,
    ) -> int:
        self.authorize(context, Role.VIEWER)
        if report_format not in {"csv", "json", "html"}:
            raise ValueError("Unsupported export format.")
        if run_id is not None:
            self._require_run(context, run_id)
        with self.connection() as conn:
            self._scope(conn, context)
            row = conn.execute(
                """
                INSERT INTO exports (workspace_id, user_id, run_id, format, content_hash)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (context.workspace_id, context.user_id, run_id, report_format, content_hash),
            ).fetchone()
        export_id = int(row["id"])
        self.audit(
            context, "report.export", "run", str(run_id) if run_id is not None else None, {"format": report_format}
        )
        return export_id

    def save_calibration_reviews(self, context: WorkspaceContext, records: list[dict[str, Any]]) -> int:
        self.authorize(context, Role.REVIEWER)
        with self.connection() as conn:
            self._scope(conn, context)
            for record in records:
                conn.execute(
                    """
                    INSERT INTO calibration_reviews
                    (workspace_id, case_id, reviewer_id, human_labels, automatic_labels, split, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(workspace_id, case_id, reviewer_id) DO UPDATE SET
                        human_labels = EXCLUDED.human_labels,
                        automatic_labels = EXCLUDED.automatic_labels,
                        split = EXCLUDED.split,
                        notes = EXCLUDED.notes,
                        created_at = now()
                    """,
                    (
                        context.workspace_id,
                        str(record["case_id"]),
                        context.user_id,
                        json.dumps(record.get("human_labels", [])),
                        json.dumps(record.get("automatic_labels", [])),
                        str(record.get("split") or "holdout"),
                        redact_pii(str(redact_secrets(record.get("notes", "")))),
                    ),
                )
        self.audit(
            context, "calibration.review.upsert", "workspace", str(context.workspace_id), {"count": len(records)}
        )
        return len(records)

    def save_calibration_result(
        self,
        context: WorkspaceContext,
        result: dict[str, Any],
        *,
        evaluator_version: str,
        dataset_version_id: int | None = None,
    ) -> int:
        self.authorize(context, Role.REVIEWER)
        with self.connection() as conn:
            self._scope(conn, context)
            if dataset_version_id is not None:
                dataset = conn.execute(
                    "SELECT id FROM dataset_versions WHERE id = %s AND workspace_id = %s",
                    (dataset_version_id, context.workspace_id),
                ).fetchone()
                if dataset is None:
                    raise AuthorizationError("Calibration dataset version does not belong to this workspace.")
            row = conn.execute(
                """
                INSERT INTO calibration_runs
                (workspace_id, dataset_version_id, evaluator_version, threshold_version,
                 calibration_version, status, reviewed_case_count, result_json, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(workspace_id, calibration_version) DO UPDATE SET
                    status = EXCLUDED.status,
                    reviewed_case_count = EXCLUDED.reviewed_case_count,
                    result_json = EXCLUDED.result_json
                RETURNING id
                """,
                (
                    context.workspace_id,
                    dataset_version_id,
                    evaluator_version,
                    result["threshold_version"],
                    result["calibration_version"],
                    result["status"],
                    int(result.get("reviewed_cases", 0)),
                    json.dumps(redact_secrets(result), default=str),
                    context.user_id,
                ),
            ).fetchone()
        calibration_id = int(row["id"])
        self.audit(
            context, "calibration.run.create", "calibration_run", str(calibration_id), {"status": result["status"]}
        )
        return calibration_id

    def latest_calibration(
        self,
        context: WorkspaceContext,
        *,
        threshold_version: str | None = None,
    ) -> dict[str, Any] | None:
        self.authorize(context, Role.VIEWER)
        query = "SELECT * FROM calibration_runs WHERE workspace_id = %s"
        parameters: list[Any] = [context.workspace_id]
        if threshold_version:
            query += " AND threshold_version = %s"
            parameters.append(threshold_version)
        query += " ORDER BY created_at DESC, id DESC LIMIT 1"
        with self.connection() as conn:
            self._scope(conn, context)
            row = conn.execute(query, parameters).fetchone()
        if row is None:
            return None
        output = dict(row)
        output["result"] = output.pop("result_json")
        return output

    def clear_results(self, context: WorkspaceContext) -> None:
        self.authorize(context, Role.ADMIN)
        with self.connection() as conn:
            self._scope(conn, context)
            conn.execute(
                "DELETE FROM comments WHERE workspace_id = %s AND execution_id IN (SELECT id FROM executions WHERE workspace_id = %s)",
                (context.workspace_id, context.workspace_id),
            )
            conn.execute(
                "DELETE FROM review_assignments WHERE workspace_id = %s AND execution_id IN (SELECT id FROM executions WHERE workspace_id = %s)",
                (context.workspace_id, context.workspace_id),
            )
            for table in ["judgments", "scores"]:
                conn.execute(
                    f"DELETE FROM {table} WHERE workspace_id = %s AND execution_id IN (SELECT id FROM executions WHERE workspace_id = %s)",  # noqa: S608 - fixed allowlist
                    (context.workspace_id, context.workspace_id),
                )
            conn.execute("UPDATE exports SET run_id = NULL WHERE workspace_id = %s", (context.workspace_id,))
            conn.execute("DELETE FROM eval_results WHERE workspace_id = %s", (context.workspace_id,))
            conn.execute("DELETE FROM executions WHERE workspace_id = %s", (context.workspace_id,))
            conn.execute("DELETE FROM eval_runs WHERE workspace_id = %s", (context.workspace_id,))
        self.audit(context, "results.clear", "workspace", str(context.workspace_id), {})

    def reset_workspace(self, context: WorkspaceContext) -> None:
        self.authorize(context, Role.OWNER)
        self.clear_results(context)
        with self.connection() as conn:
            self._scope(conn, context)
            conn.execute(
                "UPDATE prompts SET current_version_id = NULL WHERE workspace_id = %s", (context.workspace_id,)
            )
            for table in [
                "chunks",
                "document_versions",
                "documents",
                "prompt_versions",
                "prompts",
                "dataset_versions",
                "datasets",
                "target_versions",
                "targets",
                "scheduled_evaluations",
                "execution_cache",
                "projects",
            ]:
                conn.execute(
                    f"DELETE FROM {table} WHERE workspace_id = %s",  # noqa: S608 - fixed allowlist
                    (context.workspace_id,),
                )
        self.audit(context, "workspace.reset", "workspace", str(context.workspace_id), {})

    def audit(
        self,
        context: WorkspaceContext,
        action: str,
        entity_type: str,
        entity_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        self.authorize(context, Role.VIEWER)
        with self.connection() as conn:
            self._scope(conn, context)
            conn.execute(
                """
                INSERT INTO audit_logs
                (workspace_id, user_id, action, entity_type, entity_id, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    context.workspace_id,
                    context.user_id,
                    action,
                    entity_type,
                    entity_id,
                    json.dumps(redact_secrets(metadata, preserve_references=False)),
                ),
            )

    def purge_expired_data(self, context: WorkspaceContext) -> int:
        self.authorize(context, Role.OWNER)
        with self.connection() as conn:
            self._scope(conn, context)
            rows = conn.execute(
                """
                SELECT id FROM eval_runs WHERE workspace_id = %s
                 AND timestamp < now() - (SELECT retention_days FROM workspaces WHERE id = %s) * interval '1 day'
                """,
                (context.workspace_id, context.workspace_id),
            ).fetchall()
            run_ids = [int(row["id"]) for row in rows]
            for run_id in run_ids:
                conn.execute(
                    "DELETE FROM comments WHERE workspace_id = %s AND execution_id IN (SELECT id FROM executions WHERE workspace_id = %s AND run_id = %s)",
                    (context.workspace_id, context.workspace_id, run_id),
                )
                conn.execute(
                    "DELETE FROM review_assignments WHERE workspace_id = %s AND execution_id IN (SELECT id FROM executions WHERE workspace_id = %s AND run_id = %s)",
                    (context.workspace_id, context.workspace_id, run_id),
                )
                for table in ["judgments", "scores"]:
                    conn.execute(
                        f"DELETE FROM {table} WHERE workspace_id = %s AND execution_id IN (SELECT id FROM executions WHERE workspace_id = %s AND run_id = %s)",  # noqa: S608 - fixed allowlist
                        (context.workspace_id, context.workspace_id, run_id),
                    )
                conn.execute(
                    "UPDATE exports SET run_id = NULL WHERE workspace_id = %s AND run_id = %s",
                    (context.workspace_id, run_id),
                )
                conn.execute(
                    "DELETE FROM eval_results WHERE workspace_id = %s AND run_id = %s",
                    (context.workspace_id, run_id),
                )
                conn.execute(
                    "DELETE FROM executions WHERE workspace_id = %s AND run_id = %s",
                    (context.workspace_id, run_id),
                )
                conn.execute(
                    "DELETE FROM eval_runs WHERE workspace_id = %s AND id = %s",
                    (context.workspace_id, run_id),
                )
        self.audit(context, "retention.purge", "workspace", str(context.workspace_id), {"runs": len(run_ids)})
        return len(run_ids)

    def _bootstrap_context(
        self,
        email: str,
        workspace_name: str,
        *,
        always_create_workspace: bool = False,
    ) -> WorkspaceContext:
        self.migrate()
        with self.connection() as conn:
            user = conn.execute(
                """
                INSERT INTO users (email, display_name, auth_subject)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
                RETURNING id
                """,
                (email.lower(), email.split("@")[0], f"email:{email.lower()}"),
            ).fetchone()
            user_id = int(user["id"])
            membership = None
            if not always_create_workspace:
                membership = conn.execute(
                    """
                    SELECT m.workspace_id, m.role FROM memberships m JOIN workspaces w ON w.id = m.workspace_id
                    WHERE m.user_id = %s AND w.name = %s ORDER BY m.workspace_id LIMIT 1
                    """,
                    (user_id, workspace_name),
                ).fetchone()
            if membership:
                return WorkspaceContext(user_id, int(membership["workspace_id"]), Role(str(membership["role"])))
            workspace = conn.execute(
                "INSERT INTO workspaces (name, retention_days) VALUES (%s, %s) RETURNING id",
                (workspace_name, config.RETENTION_DAYS),
            ).fetchone()
            workspace_id = int(workspace["id"])
            conn.execute(
                "INSERT INTO memberships (user_id, workspace_id, role) VALUES (%s, %s, 'owner')",
                (user_id, workspace_id),
            )
        return WorkspaceContext(user_id, workspace_id, Role.OWNER)

    def _require_project(self, context: WorkspaceContext, project_id: int | None, *, allow_none: bool) -> None:
        if project_id is None and allow_none:
            return
        with self.connection() as conn:
            self._scope(conn, context)
            row = conn.execute(
                "SELECT id FROM projects WHERE id = %s AND workspace_id = %s",
                (project_id, context.workspace_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("Project does not belong to the active workspace.")

    def _require_run(self, context: WorkspaceContext, run_id: int) -> None:
        with self.connection() as conn:
            self._scope(conn, context)
            row = conn.execute(
                "SELECT id FROM eval_runs WHERE id = %s AND workspace_id = %s",
                (run_id, context.workspace_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("Run does not belong to the active workspace.")

    def _require_dataset_version(
        self,
        context: WorkspaceContext,
        dataset_version_id: int | None,
        project_id: int | None,
    ) -> None:
        if dataset_version_id is None:
            return
        with self.connection() as conn:
            self._scope(conn, context)
            row = conn.execute(
                """
                SELECT dv.id FROM dataset_versions dv JOIN datasets d ON d.id = dv.dataset_id
                WHERE dv.id = %s AND dv.workspace_id = %s AND d.workspace_id = %s
                  AND d.project_id IS NOT DISTINCT FROM %s
                """,
                (dataset_version_id, context.workspace_id, context.workspace_id, project_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("Dataset version does not belong to this workspace and project.")

    @staticmethod
    def _scope(conn: Any, context: WorkspaceContext) -> None:
        conn.execute("SELECT set_config('ars.workspace_id', %s, true)", (str(context.workspace_id),))
        conn.execute("SELECT set_config('ars.user_id', %s, true)", (str(context.user_id),))

    @staticmethod
    def _persist_postgres_judge(
        conn: Any,
        context: WorkspaceContext,
        execution_id: int,
        result: dict[str, Any],
    ) -> None:
        judge = dict(result.get("score_explanation", {}).get("judge") or {})
        if not judge:
            return
        settings = dict(judge.get("configuration") or {})
        conn.execute(
            """
            INSERT INTO judgments
            (workspace_id, execution_id, evaluator_type, provider, model, prompt, prompt_hash,
             temperature, output_json, confidence)
            VALUES (%s, %s, 'llm_judge', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                context.workspace_id,
                execution_id,
                settings.get("provider"),
                settings.get("model"),
                settings.get("prompt_template"),
                settings.get("prompt_hash"),
                settings.get("temperature"),
                json.dumps(judge, default=str),
                judge.get("confidence"),
            ),
        )


def repository_from_url(database_url: str | None = None) -> Repository:
    value = database_url or config.DATABASE_URL
    if value.startswith(("postgresql://", "postgres://")):
        return PostgresRepository(value)
    if value.startswith("sqlite:///"):
        return SQLiteRepository(value.removeprefix("sqlite:///"))
    return SQLiteRepository(value)
