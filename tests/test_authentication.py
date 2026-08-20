from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src import config
from src.auth import AuthenticatedIdentity, AuthenticationError, authenticate_request, workspace_context
from src.security import AuthorizationError
from src.storage import SQLiteRepository


def _proxy_headers(issued_at: datetime | None = None) -> dict[str, str]:
    headers = {
        "X-Auth-Subject": "oidc|user-123",
        "X-Auth-Email": "user@example.com",
        "X-Auth-Name": "Test User",
    }
    if issued_at is not None:
        headers["X-Auth-Issued-At"] = issued_at.isoformat()
    return headers


def test_proxy_identity_requires_fresh_non_spoofable_header_shape(monkeypatch):
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    monkeypatch.setattr(config, "AUTH_REQUIRE_ISSUED_AT", True)
    monkeypatch.setattr(config, "AUTH_SESSION_MAX_AGE_SECONDS", 300)
    monkeypatch.setenv("AUTH_TRUSTED_PROXY", "true")
    monkeypatch.setenv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com")

    with pytest.raises(AuthenticationError, match="issue time"):
        authenticate_request(_proxy_headers(), now=now)
    with pytest.raises(AuthenticationError, match="expired"):
        authenticate_request(_proxy_headers(now - timedelta(minutes=10)), now=now)
    with pytest.raises(AuthenticationError, match="future"):
        authenticate_request(_proxy_headers(now + timedelta(minutes=2)), now=now)
    with pytest.raises(AuthenticationError, match="control characters"):
        authenticate_request({**_proxy_headers(now), "X-Auth-Name": "User\r\nX-Admin: true"}, now=now)

    identity = authenticate_request(_proxy_headers(now - timedelta(seconds=30)), now=now)
    assert identity.subject == "oidc|user-123"
    assert identity.issued_at == now - timedelta(seconds=30)


def test_unknown_disabled_revoked_and_stale_sessions_fail_closed(tmp_path, monkeypatch):
    repository = SQLiteRepository(tmp_path / "auth.sqlite3")
    context = repository.create_workspace("user@example.com", "Secure Workspace")
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    issued_at = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    identity = AuthenticatedIdentity("oidc|user-123", "user@example.com", "User", issued_at)

    with pytest.raises(AuthenticationError, match="not been provisioned"):
        workspace_context(repository, identity)

    with repository.connection() as conn:
        conn.execute("UPDATE users SET auth_subject = ? WHERE id = ?", (identity.subject, context.user_id))
    resolved = workspace_context(repository, identity, context.workspace_id)
    assert resolved.workspace_id == context.workspace_id
    with repository.connection() as conn:
        event = conn.execute(
            "SELECT action FROM audit_logs WHERE workspace_id = ? ORDER BY id DESC LIMIT 1",
            (context.workspace_id,),
        ).fetchone()
    assert event["action"] == "auth.session.authorized"

    with repository.connection() as conn:
        conn.execute("UPDATE users SET disabled_at = ? WHERE id = ?", (issued_at.isoformat(), context.user_id))
    with pytest.raises(AuthenticationError, match="disabled"):
        workspace_context(repository, identity, context.workspace_id)

    with repository.connection() as conn:
        conn.execute(
            "UPDATE users SET disabled_at = NULL, session_not_before = ? WHERE id = ?",
            ((issued_at + timedelta(minutes=1)).isoformat(), context.user_id),
        )
    with pytest.raises(AuthenticationError, match="revocation time"):
        workspace_context(repository, identity, context.workspace_id)

    fresh_identity = AuthenticatedIdentity(
        identity.subject,
        identity.email,
        identity.display_name,
        issued_at + timedelta(minutes=2),
    )
    assert workspace_context(repository, fresh_identity, context.workspace_id).workspace_id == context.workspace_id

    with repository.connection() as conn:
        conn.execute(
            "UPDATE memberships SET revoked_at = ? WHERE user_id = ? AND workspace_id = ?",
            (issued_at.isoformat(), context.user_id, context.workspace_id),
        )
    with pytest.raises(AuthorizationError, match="no membership"):
        workspace_context(repository, fresh_identity, context.workspace_id)


def test_production_single_user_remains_refused(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    monkeypatch.setattr(config, "APP_ENV", "production")
    with pytest.raises(AuthenticationError, match="disabled in production"):
        authenticate_request()
