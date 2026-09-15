from __future__ import annotations

from contextvars import Context

import pytest

from src import config, database
from src.auth import AuthenticationError
from src.domain import ExecutionStatus
from src.public_sessions import end_public_session
from src.security import redact_secrets
from src.storage import EphemeralSQLiteRepository, SQLiteRepository
from src.targets import (
    ExternalHTTPTarget,
    ExternalTargetConfig,
    FoundationModelConfig,
    FoundationModelTarget,
    SecretResolver,
)


def test_native_browser_flag_cannot_open_storage_or_resolve_provider_key(monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "browser")
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(config, "PROVIDER_API_KEYS", {"openai": "host-only-key"})
    assert not config.is_browser_runtime()
    assert config.api_key_for_provider("openai") == ""
    state = {"documents": ["old-content"]}
    with pytest.raises(AuthenticationError, match="WebAssembly"):
        database.initialize_session(state)
    assert state == {}
    with pytest.raises(AuthenticationError):
        database.get_repository()
    target = FoundationModelTarget(FoundationModelConfig("openai", "gpt-4o-mini", "secret://KEY"))
    assert target.execute({"question": "test"}).status == ExecutionStatus.INVALID_RESPONSE


def test_verified_browser_memory_is_unique_and_never_calls_arbitrary_http(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "browser")
    monkeypatch.setattr(config.sys, "platform", "emscripten")
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ("assistant.example.test",))
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "never.sqlite3")
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{config.DATABASE_PATH}")
    first, second = {}, {}
    try:
        one = database.initialize_session(first)
        repository = database.get_repository()
        assert isinstance(repository, EphemeralSQLiteRepository)
        database.save_project({"name": "One"})
        two = database.initialize_session(second)
        assert one != two
        assert database.get_repository().list_projects(two) == []
        database.initialize_session(first)
        assert database.get_repository().list_projects(one)[0]["name"] == "One"
        with pytest.raises(AuthenticationError):
            Context().run(database.get_repository)
        with pytest.raises(PermissionError):
            database.bind_context(SQLiteRepository(tmp_path / "private.sqlite3"), one)
        target = ExternalHTTPTarget(
            ExternalTargetConfig(name="Unreachable", endpoint="https://assistant.example.test"),
            opener=lambda *args, **kwargs: pytest.fail("Browser may not send arbitrary HTTP"),
        )
        assert target.execute({"question": "test"}).status == ExecutionStatus.INVALID_RESPONSE
        assert target.health_check().status == ExecutionStatus.INVALID_RESPONSE
        assert not config.DATABASE_PATH.exists()
    finally:
        end_public_session(first)
        end_public_session(second)


def test_numeric_token_fields_do_not_allow_credential_strings(monkeypatch):
    assert redact_secrets({"input_tokens": 17, "max_tokens": 2048}) == {"input_tokens": 17, "max_tokens": 2048}
    assert redact_secrets({"input_tokens": "sensitive-key", "max_tokens": True}) == {
        "input_tokens": "[REDACTED]",
        "max_tokens": "[REDACTED]",
    }
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "public-demo")
    monkeypatch.setenv("APPROVED_KEY", "host-only-key")
    with pytest.raises(ValueError, match="not configured"):
        SecretResolver(environment_names=["APPROVED_KEY"]).resolve("secret://APPROVED_KEY")
