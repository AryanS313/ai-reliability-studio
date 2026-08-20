from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.domain import Role, WorkspaceContext
from src.security import AuthorizationError
from src.storage import SQLiteRepository, utcnow


@dataclass(frozen=True)
class ReviewQueuePolicy:
    confidence_threshold: float = 0.65
    include_severities: tuple[str, ...] = ("critical", "high")
    random_sample_rate: float = 0.05
    seed: int = 17


def build_review_queue(df: pd.DataFrame, policy: ReviewQueuePolicy | None = None) -> pd.DataFrame:
    policy = policy or ReviewQueuePolicy()
    if df.empty:
        return df.copy()
    rng = random.Random(policy.seed)  # noqa: S311 - deterministic quality-control sampling
    rows = []
    for _, row in df.iterrows():
        reasons = []
        if float(row.get("evaluator_confidence") or 0) < policy.confidence_threshold:
            reasons.append("low_evaluator_confidence")
        if str(row.get("severity", "")).lower() in policy.include_severities:
            reasons.append("severe_case")
        if bool(row.get("evaluator_disagreement", False)):
            reasons.append("evaluator_disagreement")
        if bool(row.get("regression", False)):
            reasons.append("regression")
        if rng.random() < policy.random_sample_rate:
            reasons.append("random_quality_control")
        if reasons:
            value = row.to_dict()
            value["review_reasons"] = reasons
            rows.append(value)
    return pd.DataFrame(rows)


class ReviewService:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def assign(
        self,
        context: WorkspaceContext,
        execution_id: int,
        *,
        reviewer_id: int | None,
        reason: str,
    ) -> int:
        self.repository.authorize(context, Role.REVIEWER)
        self._require_execution(context, execution_id)
        with self.repository.connection() as conn:
            assignment_cursor = conn.execute(
                """
                    INSERT INTO review_assignments
                    (workspace_id, execution_id, reviewer_id, reason, status, created_at)
                    VALUES (?, ?, ?, ?, 'needs_review', ?)
                    """,
                (context.workspace_id, execution_id, reviewer_id, reason, utcnow()),
            )
            assignment_id = _lastrowid(assignment_cursor)
        self.repository.audit(context, "review.assign", "execution", str(execution_id), {"reviewer_id": reviewer_id})
        return assignment_id

    def add_comment(
        self,
        context: WorkspaceContext,
        execution_id: int,
        body: str,
        parent_id: int | None = None,
    ) -> int:
        self.repository.authorize(context, Role.REVIEWER)
        self._require_execution(context, execution_id)
        if not body.strip():
            raise ValueError("Review comments cannot be blank.")
        with self.repository.connection() as conn:
            comment_cursor = conn.execute(
                """
                    INSERT INTO comments
                    (workspace_id, execution_id, author_id, parent_id, body, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'open', ?)
                    """,
                (context.workspace_id, execution_id, context.user_id, parent_id, body.strip(), utcnow()),
            )
            comment_id = _lastrowid(comment_cursor)
        self.repository.audit(context, "review.comment.create", "comment", str(comment_id), {})
        return comment_id

    def resolve(
        self,
        context: WorkspaceContext,
        assignment_id: int,
        *,
        human_score: float,
        decision: str,
        disagrees_with_automated: bool,
    ) -> None:
        self.repository.authorize(context, Role.REVIEWER)
        if not 0 <= human_score <= 1:
            raise ValueError("human_score must be between 0 and 1")
        with self.repository.connection() as conn:
            row = conn.execute(
                "SELECT id FROM review_assignments WHERE id = ? AND workspace_id = ?",
                (assignment_id, context.workspace_id),
            ).fetchone()
            if row is None:
                raise AuthorizationError("Review assignment does not belong to this workspace.")
            conn.execute(
                """
                UPDATE review_assignments SET status = 'resolved', human_score = ?, decision = ?,
                    automated_disagreement = ?, resolved_at = ?
                WHERE id = ? AND workspace_id = ?
                """,
                (human_score, decision, int(disagrees_with_automated), utcnow(), assignment_id, context.workspace_id),
            )
        self.repository.audit(
            context, "review.resolve", "review_assignment", str(assignment_id), {"decision": decision}
        )

    def evaluator_accuracy(self, context: WorkspaceContext) -> dict[str, Any]:
        self.repository.authorize(context, Role.REVIEWER)
        with self.repository.connection() as conn:
            rows = conn.execute(
                """
                SELECT human_score, automated_disagreement FROM review_assignments
                WHERE workspace_id = ? AND status = 'resolved' AND human_score IS NOT NULL
                """,
                (context.workspace_id,),
            ).fetchall()
        if not rows:
            return {
                "reviewed": 0,
                "agreement_rate": None,
                "notice": "Human data is measured only; automated scoring is not modified.",
            }
        return {
            "reviewed": len(rows),
            "agreement_rate": sum(not bool(row["automated_disagreement"]) for row in rows) / len(rows),
            "mean_human_score": sum(float(row["human_score"]) for row in rows) / len(rows),
            "notice": "Human data is measured only; automated scoring is not modified without explicit configuration.",
        }

    def _require_execution(self, context: WorkspaceContext, execution_id: int) -> None:
        with self.repository.connection() as conn:
            row = conn.execute(
                "SELECT id FROM executions WHERE id = ? AND workspace_id = ?",
                (execution_id, context.workspace_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("Execution does not belong to this workspace.")


def _lastrowid(cursor: Any) -> int:
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite insert did not return a row id.")
    return int(cursor.lastrowid)
