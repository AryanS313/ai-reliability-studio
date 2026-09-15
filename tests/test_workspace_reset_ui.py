from __future__ import annotations

import socket
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.storage import EphemeralSQLiteRepository, SQLiteRepository


@pytest.fixture
def reset_app(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    monkeypatch.setattr(config, "PUBLIC_SESSION_TTL_SECONDS", 86400)
    monkeypatch.setattr(config, "api_key_for_provider", lambda provider: "")

    def no_network(*args, **kwargs):
        raise AssertionError("Reset checks must not contact the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: False if path.name in {"secrets.toml", ".env"} else original_is_file(path),
    )
    apps = []
    database.set_repository(None)

    def create(mode="browser"):
        monkeypatch.setattr(config, "APP_ACCESS_MODE", mode)
        monkeypatch.setattr(config, "AUTH_MODE", "single-user")
        monkeypatch.setattr(config, "is_browser_runtime", lambda: mode == "browser")
        monkeypatch.setattr(config, "browser_runtime_enabled", lambda: mode == "browser")
        if mode == "local":
            repository = SQLiteRepository(tmp_path / "persistent.sqlite3")
            monkeypatch.setattr(database, "repository_from_url", lambda: repository)
            database.set_repository(repository)
        app = AppTest.from_file(str(config.ROOT_DIR / "app.py")).run(timeout=30)
        apps.append(app)
        assert not app.exception
        return app

    yield create
    for app in apps:
        if "_studio_private_session" in app.session_state:
            app.session_state["_studio_private_session"].close()
    database.set_repository(None)


def add_review(app):
    app.button(key="start_saved_sample").click().run(timeout=30)
    next(widget for widget in app.selectbox if widget.label == "Decision").set_value("Supported by the sources")
    next(widget for widget in app.text_area if widget.label == "What in the source supports your decision?").set_value(
        "The source passage states 24 hours, matching this answer."
    )
    next(widget for widget in app.text_input if widget.label == "Reviewer name").set_value("Reset regression reviewer")
    next(widget for widget in app.checkbox if widget.label.startswith("I checked this answer")).check()
    next(widget for widget in app.button if widget.label == "Save review and continue").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["offline_baseline"]["review_status"].eq("reviewed").sum() == 1
    app.session_state["provider_api_keys"] = {
        "openai": "fictional-reset-check",
        "anthropic": "",
        "gemini": "",
    }


def assert_empty_workspace(app):
    assert not app.session_state["offline_workspace"]
    assert app.session_state["offline_baseline"].empty
    assert app.session_state["offline_candidate"].empty
    assert app.session_state["project_id"] is None
    assert not app.session_state["documents"]
    assert not app.session_state["chunks"]
    assert app.session_state["eval_df"].empty
    assert app.session_state["last_results"].empty
    assert not any(app.session_state["provider_api_keys"].values())
    assert not app.session_state["privacy_acknowledged"]


def reset_all(app):
    app.selectbox(key="advanced_tool").set_value("Settings / Export").run(timeout=30)
    button = next(widget for widget in app.button if widget.label == "Reset workspace")
    assert button.disabled
    next(widget for widget in app.text_input if widget.label.startswith("Type DELETE WORKSPACE DATA")).set_value(
        "DELETE WORKSPACE DATA"
    ).run(timeout=30)
    next(widget for widget in app.button if widget.label == "Reset workspace").click().run(timeout=30)
    assert not app.exception
    assert_empty_workspace(app)
    assert app.radio(key="navigation").value == "Start"
    assert app.selectbox(key="advanced_tool").value == "Choose a tool"


def test_reset_all_removes_saved_reviews_keys_and_private_db_without_touching_another_visitor(reset_app):
    first = reset_app()
    add_review(first)
    first_session = first.session_state["_studio_private_session"]
    second = reset_app()
    add_review(second)
    other_workspace = deepcopy(second.session_state["offline_workspace"])
    other_session = second.session_state["_studio_private_session"]
    other_projects = other_session.repository.list_projects(other_session.context)

    reset_all(first)

    assert first_session.closed
    assert isinstance(first_session.repository, EphemeralSQLiteRepository)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        first_session.repository.list_projects(first_session.context)
    assert first.session_state["_studio_private_session"].context != first_session.context
    assert not other_session.closed
    assert other_session.repository.list_projects(other_session.context) == other_projects
    second.run(timeout=30)
    assert not second.exception
    assert second.session_state["offline_workspace"] == other_workspace
    assert second.session_state["offline_baseline"]["review_status"].eq("reviewed").sum() == 1
    assert second.session_state["provider_api_keys"]["openai"] == "fictional-reset-check"


def test_reset_all_reinitializes_local_ui_but_retains_identity_and_reset_audit(reset_app):
    app = reset_app("local")
    add_review(app)
    repository = database.get_repository()
    context = app.session_state["workspace_context"]
    repository.create_project(context, {"name": "Reset this project"})

    reset_all(app)

    assert repository.path.exists()
    assert app.session_state["workspace_context"] == context
    assert repository.list_projects(context) == []
    with repository.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE id = ?", (context.user_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'workspace.reset'").fetchone()[0] == 1


def test_sidebar_and_sample_remain_functional_after_two_workspace_resets(reset_app):
    app = reset_app()
    for _cycle in range(2):
        app.selectbox(key="advanced_tool").set_value("Choose a tool").run(timeout=30)
        app.radio(key="navigation").set_value("Start").run(timeout=30)
        add_review(app)
        reset_all(app)
        assert app.radio(key="navigation").proto.set_value, "Reset must synchronize the mounted browser radio"
        app.selectbox(key="advanced_tool").set_value("Settings / Export").run(timeout=30)
        assert not app.exception
        assert any(widget.value == "Export and workspace settings" for widget in app.title)
        app.selectbox(key="advanced_tool").set_value("Review saved answers").run(timeout=30)
        assert not app.exception
        assert not any(widget.label == "Import answers" for widget in app.button)
        app.checkbox(key="privacy_acknowledgement_control").check().run(timeout=30)
        assert any("Create or reopen a project first" in item.value for item in app.info)
        app.radio(key="navigation").set_value("Prepare").run(timeout=30)
        next(widget for widget in app.text_input if widget.label == "Project name").set_value("After reset")
        next(widget for widget in app.button if widget.label == "Create project").click().run(timeout=30)
        app.selectbox(key="advanced_tool").set_value("Review saved answers").run(timeout=30)
        assert not app.exception
        assert any(widget.label == "Import answers" for widget in app.button)
        assert not app.session_state["offline_workspace"]
        app.radio(key="navigation").set_value("Start").run(timeout=30)
        assert not app.exception
        app.button(key="start_saved_sample").click().run(timeout=30)
        assert not app.exception
        assert app.session_state["offline_baseline"]["review_status"].eq("pending").all()
        assert len(app.session_state["offline_baseline"]) == 3
