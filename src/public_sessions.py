"""Memory-only anonymous workspaces, rebound before every Streamlit rerun.

Hosted sessions accept approved custom inputs and visitor-supplied keys. Explicit
public demos accept fictional sample data. A verified WebAssembly browser may
also review custom answers and use session-supplied provider keys. No anonymous mode
opens the configured DB. Memory expires on idle cleanup, reset or process exit.
"""

from __future__ import annotations

import threading
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
from weakref import WeakSet

from src import config, database, hosted_limits
from src.auth import authenticate_request
from src.domain import Role, WorkspaceContext
from src.storage import EphemeralSQLiteRepository, Repository, utcnow

_SESSION_KEY = "_studio_private_session"
_sessions: WeakSet[PublicSession] = WeakSet()
_sessions_lock = threading.RLock()


@dataclass(frozen=True)
class SessionInitialization:
    repository: Repository
    context: WorkspaceContext
    ephemeral: bool
    notice: str
    new_session: bool = False


class PublicSession:
    def __init__(self, *, temporary_root: Path | None = None) -> None:
        self.access_mode = config.APP_ACCESS_MODE
        self.budget = hosted_limits.new_session_budget() if config.hosted_sessions_enabled() else None
        self.repository = EphemeralSQLiteRepository()
        hosted_limits.bind_repository(self.repository, self.budget)
        self.repository.migrate()
        # Session-specific IDs prevent a stale context from another private DB
        # accidentally matching its independently allocated integer IDs.
        user_id = uuid4().int & ((1 << 63) - 1)
        workspace_id = uuid4().int & ((1 << 63) - 1)
        session_id = uuid4().hex
        with self.repository.connection() as conn:
            if self.budget is not None:
                page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
                page_limit = hosted_limits.HOSTED_MAX_SESSION_DATABASE_BYTES // page_size
                conn.execute(f"PRAGMA max_page_count = {page_limit}")
            # Migrations seed a development workspace. This database is brand
            # new, so remove that seed to reject stale development contexts.
            conn.execute("DELETE FROM memberships")
            conn.execute("DELETE FROM workspaces")
            conn.execute("DELETE FROM users")
            conn.execute(
                "INSERT INTO users (id, email, display_name, auth_subject, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, f"{session_id}@public-session.invalid", "Anonymous visitor", session_id, utcnow()),
            )
            conn.execute(
                "INSERT INTO workspaces (id, name, retention_days, pii_redaction_enabled, created_at) VALUES (?, ?, ?, 0, ?)",
                (workspace_id, "Private temporary workspace", 1, utcnow()),
            )
            conn.execute(
                "INSERT INTO memberships (user_id, workspace_id, role, created_at) VALUES (?, ?, 'owner', ?)",
                (user_id, workspace_id, utcnow()),
            )
        self.context = WorkspaceContext(user_id=user_id, workspace_id=workspace_id, role=Role.OWNER)
        self.last_used = time.monotonic()
        self.closed = False
        with _sessions_lock:
            _sessions.add(self)

    def close(self) -> None:
        """Close this session's memory database only; never the configured DB."""
        with _sessions_lock:
            if self.budget is not None:
                self.budget.close()
            self.repository.close()
            self.closed = True
            _sessions.discard(self)


def cleanup_expired_sessions(*, now: float | None = None) -> int:
    """Close idle memory databases when the application next receives a request."""
    ttl = config.PUBLIC_SESSION_TTL_SECONDS
    if ttl <= 0:
        raise ValueError("PUBLIC_SESSION_TTL_SECONDS must be positive.")
    current = time.monotonic() if now is None else now
    removed = 0
    with _sessions_lock:
        for session in list(_sessions):
            if current - session.last_used >= ttl:
                session.close()
                removed += 1
    return removed


def end_public_session(state: MutableMapping[str, Any]) -> None:
    """Explicit delete/reset: erase the private DB, uploads in state, and keys."""
    session = state.get(_SESSION_KEY)
    if isinstance(session, PublicSession):
        session.close()
    state.clear()
    database.clear_request()


def initialize_session(
    state: MutableMapping[str, Any],
    request_headers: dict[str, Any] | None = None,
    *,
    temporary_root: Path | None = None,
) -> SessionInitialization:
    """Authenticate or rebind an isolated memory workspace before every rerun."""
    database.clear_request()
    try:
        database._validate_access_mode()
    except PermissionError:
        state.clear()
        raise
    if not config.public_sessions_enabled():
        previous = state.pop(_SESSION_KEY, None)
        if isinstance(previous, PublicSession):
            previous.close()
            state.clear()
        try:
            database._validate_access_mode()
            authenticate_request(request_headers)
            database.init_db()
            context = database.current_context(request_headers)
        except PermissionError:
            state.clear()
            raise
        previous_context = state.get("workspace_context")
        if previous_context is not None and previous_context != context:
            state.clear()
            database.clear_request()
            from src.auth import AuthenticationError

            raise AuthenticationError("The workspace identity changed. Reload to begin a clean session.")
        state["workspace_context"] = context
        return SessionInitialization(database.get_repository(), context, False, "")

    with _sessions_lock:
        cleanup_expired_sessions()
        session = state.get(_SESSION_KEY)
        created = (
            not isinstance(session, PublicSession) or session.closed or session.access_mode != config.APP_ACCESS_MODE
        )
        if created:
            if isinstance(session, PublicSession):
                session.close()
            # In particular, discard any previous single-user data and API keys.
            state.clear()
            session = PublicSession(temporary_root=temporary_root)
            state[_SESSION_KEY] = session
        if not isinstance(session, PublicSession):  # Defensive guard for custom state implementations.
            raise RuntimeError("Private session initialization failed.")
        session.last_used = time.monotonic()
        database.bind_context(session.repository, session.context)
        state["workspace_context"] = session.context
    hours = config.PUBLIC_SESSION_TTL_SECONDS / 3600
    notice = (
        f"Your workspace is private to this browser session and temporary. "
        f"It expires after {hours:g} hours of inactivity or a server restart. "
        "This public demo accepts fictional samples only. Export results before leaving."
    )
    if config.hosted_sessions_enabled():
        notice = (
            "Your work is held in this session's private server memory. It is not shared with other visitors. "
            f"It expires after {hours:g} hours of inactivity, a reset or server restart. "
            "Download your work before leaving. Only keys you enter are used; real calls send selected inputs "
            "to your chosen provider or public HTTPS assistant. Use approved, non-sensitive test data."
        )
    elif config.is_browser_runtime():
        notice = (
            "Your workspace stays in this tab's memory. Closing or reloading the tab clears it, "
            f"as does returning after {hours:g} hours of inactivity. "
            "Download your workspace to keep it and resume later. "
            "Provider tests send the selected questions and sources using the key you enter."
        )
    return SessionInitialization(session.repository, session.context, True, notice, created)
