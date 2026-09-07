from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.storage import SQLiteRepository


@pytest.mark.parametrize("auth_mode", ["single-user", "public-session"])
def test_new_ui_renders_with_config_cached_from_before_browser_release(monkeypatch, tmp_path, auth_mode):
    # A running Streamlit process can rerun the new app.py while src.config is
    # still cached from release 1, which did not have this helper.
    monkeypatch.delattr(config, "browser_runtime_enabled", raising=False)
    monkeypatch.setattr(config, "AUTH_MODE", auth_mode)
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    repository = SQLiteRepository(tmp_path / "runtime-reload.sqlite3")
    monkeypatch.setattr(database, "repository_from_url", lambda: repository)
    database.set_repository(repository)
    app = AppTest.from_file("app.py")
    try:
        app.run(timeout=30)
        assert not app.exception
        assert app.button(key="start_live")
        app.button(key="start_sample").click().run(timeout=30)
        assert not app.exception
        assert len(app.session_state["offline_baseline"]) == 3
        app.radio(key="page").set_value("Run Evaluation").run(timeout=30)
        assert not app.exception
        assert any(widget.label == "Concurrency" for widget in app.slider)
        app.radio(key="page").set_value("Settings / Export").run(timeout=30)
        assert not app.exception
        assert any(widget.value == "Settings / Export" for widget in app.title)
        if auth_mode == "public-session":
            assert "server restart" in app.session_state["public_session_notice"]
            assert "tab's memory" not in app.session_state["public_session_notice"]
    finally:
        if "_studio_private_session" in app.session_state:
            app.session_state["_studio_private_session"].close()
        database.set_repository(None)
