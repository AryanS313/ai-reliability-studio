from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src import config
from src.domain import Role, WorkspaceContext
from src.security import AuthorizationError
from src.storage import PostgresRepository, Repository, SQLiteRepository


class AuthenticationError(PermissionError):
    pass


@dataclass(frozen=True)
class AuthenticatedIdentity:
    subject: str
    email: str
    display_name: str
    issued_at: datetime | None = None


def authenticate_request(
    headers: Mapping[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> AuthenticatedIdentity:
    if config.AUTH_MODE == "single-user":
        if config.APP_ENV == "production":
            raise AuthenticationError("Single-user authentication is disabled in production.")
        return AuthenticatedIdentity(
            subject="local-user",
            email=config.SINGLE_USER_EMAIL,
            display_name="Local User",
        )
    if config.AUTH_MODE not in {"proxy", "oidc-proxy"}:
        raise AuthenticationError(f"Unsupported AUTH_MODE: {config.AUTH_MODE}")
    if os.getenv("AUTH_TRUSTED_PROXY", "").lower() not in {"true", "1", "yes"}:
        raise AuthenticationError("Proxy authentication requires AUTH_TRUSTED_PROXY=true behind a trusted proxy.")
    normalized = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    if any("\r" in value or "\n" in value for value in normalized.values()):
        raise AuthenticationError("Authentication headers contain invalid control characters.")
    subject = normalized.get("x-auth-subject", "").strip()
    email = normalized.get("x-auth-email", "").strip().lower()
    name = normalized.get("x-auth-name", "").strip() or email.split("@")[0]
    if not subject or not email or "@" not in email:
        raise AuthenticationError("Authenticated subject and email headers are required.")
    allowed_domain = os.getenv("AUTH_ALLOWED_EMAIL_DOMAIN", "").lower()
    if allowed_domain and not email.endswith("@" + allowed_domain):
        raise AuthenticationError("Authenticated email is outside the allowed domain.")
    issued_at = _issued_at(normalized.get("x-auth-issued-at", ""))
    if config.AUTH_REQUIRE_ISSUED_AT and issued_at is None:
        raise AuthenticationError("The trusted proxy must provide an identity issue time.")
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    if issued_at is not None:
        age_seconds = (current_time - issued_at).total_seconds()
        if age_seconds < -60:
            raise AuthenticationError("The authenticated identity issue time is in the future.")
        if age_seconds > config.AUTH_SESSION_MAX_AGE_SECONDS:
            raise AuthenticationError("The authenticated session has expired.")
    return AuthenticatedIdentity(subject=subject, email=email, display_name=name, issued_at=issued_at)


def workspace_context(
    repository: Repository,
    identity: AuthenticatedIdentity,
    workspace_id: int | None = None,
) -> WorkspaceContext:
    if config.AUTH_MODE == "single-user":
        return repository.local_context()
    if isinstance(repository, SQLiteRepository):
        with repository.connection() as conn:
            user = conn.execute(
                "SELECT id, disabled_at, session_not_before FROM users WHERE auth_subject = ?",
                (identity.subject,),
            ).fetchone()
            if user is None:
                raise AuthenticationError("Authenticated user has not been provisioned.")
            _validate_user_state(dict(user), identity)
            user_id = int(user["id"])
            if workspace_id is None:
                membership = conn.execute(
                    """
                    SELECT workspace_id, role FROM memberships
                    WHERE user_id = ? AND revoked_at IS NULL ORDER BY workspace_id LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
            else:
                membership = conn.execute(
                    """
                    SELECT workspace_id, role FROM memberships
                    WHERE user_id = ? AND workspace_id = ? AND revoked_at IS NULL
                    """,
                    (user_id, workspace_id),
                ).fetchone()
    elif isinstance(repository, PostgresRepository):
        with repository.connection() as conn:
            user = conn.execute(
                "SELECT id, disabled_at, session_not_before FROM users WHERE auth_subject = %s",
                (identity.subject,),
            ).fetchone()
            if user is None:
                raise AuthenticationError("Authenticated user has not been provisioned.")
            _validate_user_state(dict(user), identity)
            user_id = int(user["id"])
            conn.execute("SELECT set_config('ars.user_id', %s, true)", (str(user_id),))
            if workspace_id is None:
                membership = conn.execute(
                    """
                    SELECT workspace_id, role FROM memberships
                    WHERE user_id = %s AND revoked_at IS NULL ORDER BY workspace_id LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
            else:
                membership = conn.execute(
                    """
                    SELECT workspace_id, role FROM memberships
                    WHERE user_id = %s AND workspace_id = %s AND revoked_at IS NULL
                    """,
                    (user_id, workspace_id),
                ).fetchone()
    else:  # pragma: no cover - third-party repository implementation
        raise AuthenticationError("Repository does not expose identity lookup.")
    if membership is None:
        raise AuthorizationError("Authenticated user has no membership in the requested workspace.")
    context = WorkspaceContext(
        user_id=user_id, workspace_id=int(membership["workspace_id"]), role=Role(str(membership["role"]))
    )
    repository.audit(
        context,
        "auth.session.authorized",
        "user",
        str(user_id),
        {
            "auth_mode": config.AUTH_MODE,
            "session_issued_at": identity.issued_at.isoformat() if identity.issued_at else None,
        },
    )
    return context


def _issued_at(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        if value.strip().replace(".", "", 1).isdigit():
            parsed = datetime.fromtimestamp(float(value), tz=UTC)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise AuthenticationError("The trusted proxy supplied an invalid identity issue time.") from exc
    return parsed


def _validate_user_state(user: Mapping[str, Any], identity: AuthenticatedIdentity) -> None:
    if user.get("disabled_at"):
        raise AuthenticationError("Authenticated user is disabled.")
    session_not_before = user.get("session_not_before")
    if session_not_before:
        if identity.issued_at is None:
            raise AuthenticationError("This account requires a freshly issued authenticated session.")
        try:
            threshold = datetime.fromisoformat(str(session_not_before).replace("Z", "+00:00"))
            threshold = threshold.replace(tzinfo=UTC) if threshold.tzinfo is None else threshold.astimezone(UTC)
        except ValueError as exc:
            raise AuthenticationError("The account session policy is invalid; access is denied.") from exc
        if identity.issued_at < threshold:
            raise AuthenticationError("The authenticated session was issued before the account revocation time.")
