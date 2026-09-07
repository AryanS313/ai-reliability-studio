"""Private, temporary workspaces for an explicitly anonymous public application.

The UI must call initialize_session on EVERY rerun before any database operation.
Keep its server-created session object in Streamlit session_state, never in a URL,
cookie, shared cache, or client-supplied identifier. Exported files are the durable
copy: temporary work disappears after idle expiry, explicit deletion, session
garbage collection, or server restart. This module never opens the configured DB.
"""

from __future__ import annotations

import threading
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4
from weakref import WeakSet

from src import config, database
from src.auth import authenticate_request
from src.domain import Role, WorkspaceContext
from src.storage import Repository, SQLiteRepository, utcnow

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
        self._directory = TemporaryDirectory(prefix="studio-public-session-", dir=temporary_root)
        self.repository = SQLiteRepository(Path(self._directory.name) / "workspace.sqlite3")
        self.repository.migrate()
        # Session-specific IDs prevent a stale context from another private DB
        # accidentally matching its independently allocated integer IDs.
        user_id = uuid4().int & ((1 << 63) - 1)
        workspace_id = uuid4().int & ((1 << 63) - 1)
        session_id = uuid4().hex
        with self.repository.connection() as conn:
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
        """Delete this session's private directory only; never the configured DB."""
        with _sessions_lock:
            self._directory.cleanup()
            self.closed = True
            _sessions.discard(self)


def cleanup_expired_sessions(*, now: float | None = None) -> int:
    """Delete idle temporary sessions when the app next receives a request.

    TemporaryDirectory also cleans up when the server releases session state or
    exits normally. An abruptly killed host may leave files for its OS temporary
    storage cleanup; these cannot be resumed by a new process or public visitor.
    """
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
    """Authenticate or create/rebind a private session before every UI rerun.

    AUTH_MODE=public-session is the only anonymous opt-in. Other modes retain
    authenticate_request's fail-closed behavior, including production refusal
    of single-user authentication. The returned notice belongs beside export.
    """
    database.clear_request()
    if not config.public_sessions_enabled():
        previous = state.pop(_SESSION_KEY, None)
        if isinstance(previous, PublicSession):
            previous.close()
            state.clear()
        try:
            authenticate_request(request_headers)
            database.init_db()
            context = database.current_context(request_headers)
        except PermissionError:
            state.clear()
            raise
        previous_context = state.get("workspace_context")
        if previous_context is not None and previous_context != context:
            state.clear()
        state["workspace_context"] = context
        return SessionInitialization(database.get_repository(), context, False, "")

    with _sessions_lock:
        cleanup_expired_sessions()
        session = state.get(_SESSION_KEY)
        created = not isinstance(session, PublicSession) or session.closed
        if created:
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
        "Export your work before leaving. Provider keys must be supplied in this session."
    )
    if config.browser_runtime_enabled():
        notice = (
            "Your workspace stays in this tab's memory. Closing or reloading the tab clears it, "
            f"as does returning after {hours:g} hours of inactivity. "
            "Download your workspace to keep it and resume later. "
            "Provider tests send the selected questions and sources using the key you enter."
        )
    return SessionInitialization(session.repository, session.context, True, notice, created)
