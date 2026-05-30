from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src import config


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    if _schema_needs_reset(conn):
        _drop_app_tables(conn)
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
            chunk_count INTEGER NOT NULL,
            status TEXT NOT NULL,
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
    conn.commit()
    if own:
        conn.close()


def save_project(metadata: dict[str, str]) -> int:
    conn = connect()
    init_db(conn)
    cursor = conn.execute(
        """
        INSERT INTO projects (name, use_case, industry, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            metadata.get("name", ""),
            metadata.get("use_case", ""),
            metadata.get("industry", ""),
            metadata.get("notes", ""),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    project_id = int(cursor.lastrowid)
    conn.close()
    return project_id


def clear_database() -> None:
    conn = connect()
    init_db(conn)
    _drop_app_tables(conn)
    conn.commit()
    conn.close()
    init_db()


def clear_results() -> None:
    conn = connect()
    init_db(conn)
    conn.execute("DELETE FROM eval_results")
    conn.execute("DELETE FROM eval_runs")
    conn.commit()
    conn.close()


def save_documents_and_chunks(documents: list[dict], chunks: list[dict], project_id: int | None = None) -> None:
    conn = connect()
    init_db(conn)
    now = datetime.utcnow().isoformat()
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM documents")
    for document in documents:
        doc_chunks = [chunk for chunk in chunks if chunk["filename"] == document["filename"]]
        cursor = conn.execute(
            """
            INSERT INTO documents (project_id, filename, uploaded_at, chunk_count, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, document["filename"], now, len(doc_chunks), "indexed"),
        )
        document_id = cursor.lastrowid
        for chunk in doc_chunks:
            conn.execute(
                """
                INSERT INTO chunks (document_id, source_name, chunk_text, chunk_index)
                VALUES (?, ?, ?, ?)
                """,
                (document_id, chunk["source_name"], chunk["chunk_text"], chunk["chunk_index"]),
            )
    conn.commit()
    conn.close()


def load_chunks() -> list[dict]:
    conn = connect()
    init_db(conn)
    rows = conn.execute("SELECT source_name, chunk_text, chunk_index FROM chunks ORDER BY id").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def documents_df() -> pd.DataFrame:
    conn = connect()
    init_db(conn)
    df = pd.read_sql_query("SELECT filename, uploaded_at, chunk_count, status FROM documents ORDER BY id", conn)
    conn.close()
    return df


def save_prompt(project_id: int | None, prompt_name: str, prompt_text: str, prompt_type: str) -> None:
    conn = connect()
    init_db(conn)
    conn.execute(
        """
        INSERT INTO prompts (project_id, prompt_name, prompt_text, prompt_type, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (project_id, prompt_name, prompt_text, prompt_type, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def prompts_df() -> pd.DataFrame:
    conn = connect()
    init_db(conn)
    df = pd.read_sql_query("SELECT * FROM prompts ORDER BY id DESC", conn)
    conn.close()
    return df


def create_eval_run(
    run_name: str,
    model_name: str,
    mode: str,
    total_questions: int,
    project_id: int | None = None,
    notes: str = "",
) -> int:
    conn = connect()
    init_db(conn)
    cursor = conn.execute(
        """
        INSERT INTO eval_runs (project_id, run_name, timestamp, model_name, mode, total_questions, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, run_name, datetime.utcnow().isoformat(), model_name, mode, total_questions, notes),
    )
    conn.commit()
    run_id = int(cursor.lastrowid)
    conn.close()
    return run_id


def save_eval_result(run_id: int, result: dict[str, Any]) -> None:
    conn = connect()
    init_db(conn)
    fields = [
        "run_id",
        "question",
        "expected_answer",
        "actual_answer",
        "expected_source",
        "retrieved_sources",
        "retrieved_chunks",
        "category",
        "should_escalate",
        "actual_escalation",
        "expected_answer_match_score",
        "source_retrieval_score",
        "citation_correctness_score",
        "groundedness_score",
        "escalation_correctness_score",
        "hallucination_risk",
        "latency_ms",
        "estimated_cost",
        "overall_score",
        "failure_type",
        "suggested_fix",
        "prompt_name",
        "model_name",
        "final_prompt",
    ]
    payload = dict(result)
    payload["run_id"] = run_id
    payload["retrieved_sources"] = json.dumps(payload.get("retrieved_sources", []))
    payload["retrieved_chunks"] = json.dumps(payload.get("retrieved_chunks", []))
    values = [payload.get(field) for field in fields]
    placeholders = ", ".join(["?"] * len(fields))
    conn.execute(f"INSERT INTO eval_results ({', '.join(fields)}) VALUES ({placeholders})", values)
    conn.commit()
    conn.close()


def latest_results_df() -> pd.DataFrame:
    conn = connect()
    init_db(conn)
    df = pd.read_sql_query(
        """
        SELECT er.*, runs.run_name, runs.timestamp, runs.mode
        FROM eval_results er
        JOIN eval_runs runs ON runs.id = er.run_id
        WHERE er.run_id = (SELECT id FROM eval_runs ORDER BY timestamp DESC LIMIT 1)
        ORDER BY er.id
        """,
        conn,
    )
    conn.close()
    return df


def all_results_df() -> pd.DataFrame:
    conn = connect()
    init_db(conn)
    df = pd.read_sql_query(
        """
        SELECT er.*, runs.run_name, runs.timestamp, runs.mode
        FROM eval_results er
        JOIN eval_runs runs ON runs.id = er.run_id
        ORDER BY er.id DESC
        """,
        conn,
    )
    conn.close()
    return df


def eval_runs_df() -> pd.DataFrame:
    conn = connect()
    init_db(conn)
    df = pd.read_sql_query("SELECT * FROM eval_runs ORDER BY id DESC", conn)
    conn.close()
    return df


def _schema_needs_reset(conn: sqlite3.Connection) -> bool:
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if not tables:
        return False
    if "eval_results" in tables:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(eval_results)").fetchall()}
        return "final_prompt" not in columns or "expected_answer_match_score" not in columns
    return False


def _drop_app_tables(conn: sqlite3.Connection) -> None:
    for table in ["eval_results", "eval_runs", "chunks", "documents", "prompts", "prompt_versions", "projects"]:
        conn.execute(f"DROP TABLE IF EXISTS {table}")

