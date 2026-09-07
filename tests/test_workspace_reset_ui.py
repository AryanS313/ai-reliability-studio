from __future__ import annotations

import socket
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.storage import SQLiteRepository


@pytest.fixture
def reset_app(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    monkeypatch.setattr(config, "PUBLIC_SESSION_TTL_SECONDS", 86400)

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

    def create(mode="public-session"):
        monkeypatch.setattr(config, "AUTH_MODE", mode)
        if mode != "public-session":
            repository = SQLiteRepository(tmp_path / "persistent.sqlite3")
            monkeypatch.setattr(database, "repository_from_url", lambda: repository)
            database.set_repository(repository)
        app = AppTest.from_file("app.py").run(timeout=30)
        apps.append(app)
        assert not app.exception
        return app

    yield create
    for app in apps:
        if "_studio_private_session" in app.session_state:
            app.session_state["_studio_private_session"].close()
    database.set_repository(None)


def add_review(app):
    app.button(key="start_sample").click().run(timeout=30)
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


def reset_all(app):
    app.radio(key="page").set_value("Settings / Export").run(timeout=30)
    button = next(widget for widget in app.button if widget.label == "Reset all data in this workspace")
    assert button.disabled
    next(widget for widget in app.text_input if widget.label.startswith("Type DELETE WORKSPACE DATA")).set_value(
        "DELETE WORKSPACE DATA"
    ).run(timeout=30)
    next(widget for widget in app.button if widget.label == "Reset all data in this workspace").click().run(timeout=30)
    assert not app.exception
    assert "offline_workspace" not in app.session_state
    assert "offline_baseline" not in app.session_state
    assert "offline_candidate" not in app.session_state
    assert not any(app.session_state["provider_api_keys"].values())
    app.button(key="start_saved").click().run(timeout=30)
    assert not app.exception
    assert "offline_workspace" not in app.session_state
    assert any(widget.label == "Import answers" for widget in app.button)


def test_reset_all_removes_saved_reviews_keys_and_private_db_without_touching_another_visitor(
    reset_app,
):
    first = reset_app()
    add_review(first)
    first_session = first.session_state["_studio_private_session"]
    second = reset_app()
    add_review(second)
    other_workspace = deepcopy(second.session_state["offline_workspace"])
    other_session = second.session_state["_studio_private_session"]

    reset_all(first)

    assert first_session.closed
    assert not first_session.repository.path.exists()
    assert first.session_state["_studio_private_session"].context != first_session.context
    assert not other_session.closed
    assert other_session.repository.path.exists()
    second.run(timeout=30)
    assert not second.exception
    assert second.session_state["offline_workspace"] == other_workspace
    assert second.session_state["offline_baseline"]["review_status"].eq("reviewed").sum() == 1
    assert second.session_state["provider_api_keys"]["openai"] == "fictional-reset-check"


def test_reset_all_reinitializes_local_ui_but_retains_identity_and_reset_audit(
    reset_app,
):
    app = reset_app("single-user")
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
        app.radio(key="page").set_value("Overview").run(timeout=30)
        add_review(app)
        app.radio(key="page").set_value("Settings / Export").run(timeout=30)
        next(w for w in app.text_input if w.label.startswith("Type DELETE WORKSPACE DATA")).set_value(
            "DELETE WORKSPACE DATA"
        ).run(timeout=30)
        next(w for w in app.button if w.label == "Reset all data in this workspace").click().run(timeout=30)
        assert not app.exception
        assert "offline_workspace" not in app.session_state
        assert app.radio(key="page").value == "Overview"
        assert app.radio(key="page").proto.set_value, "Reset must explicitly synchronize the mounted browser radio"
        app.radio(key="page").set_value("Settings / Export").run(timeout=30)
        assert not app.exception
        assert any(w.value == "Settings / Export" for w in app.title)
        app.radio(key="page").set_value("Review saved answers").run(timeout=30)
        assert not app.exception
        assert any(w.label == "Import answers" for w in app.button)
        app.radio(key="page").set_value("Overview").run(timeout=30)
        assert not app.exception
        app.button(key="start_sample").click().run(timeout=30)
        assert not app.exception
        assert app.session_state["offline_baseline"]["review_status"].eq("pending").all()
        assert len(app.session_state["offline_baseline"]) == 3
