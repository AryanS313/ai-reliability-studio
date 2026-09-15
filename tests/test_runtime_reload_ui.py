from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.storage import SQLiteRepository


@pytest.mark.parametrize("access_mode", ["local", "public-demo", "browser"])
def test_new_ui_renders_with_config_cached_from_before_browser_release(monkeypatch, tmp_path, access_mode):
    # Streamlit can rerun new app.py while an older src.config remains cached.
    # Keep the compatibility helper absent; emulate browser capability separately.
    monkeypatch.delattr(config, "browser_runtime_enabled", raising=False)
    monkeypatch.setattr(config, "APP_ACCESS_MODE", access_mode)
    monkeypatch.setattr(config, "is_browser_runtime", lambda: access_mode == "browser")
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    repository = SQLiteRepository(tmp_path / "runtime-reload.sqlite3")
    monkeypatch.setattr(database, "repository_from_url", lambda: repository)
    database.set_repository(repository)
    app = AppTest.from_file(str(config.ROOT_DIR / "app.py"))
    try:
        app.run(timeout=30)
        assert not app.exception
        assert app.radio(key="navigation").options == ["Start", "Prepare", "Connect", "Evaluate", "Review", "History"]
        assert any(widget.key == "start_live" for widget in app.button) == (access_mode != "public-demo")
        app.button(key="start_saved_sample").click().run(timeout=30)
        assert not app.exception
        assert len(app.session_state["offline_baseline"]) == 3
        app.radio(key="navigation").set_value("Evaluate").run(timeout=30)
        assert not app.exception
        if access_mode == "browser":
            assert not any(widget.label == "Concurrency" for widget in app.slider)
            assert any("One question runs at a time" in item.value for item in app.caption)
        else:
            assert any(widget.label == "Concurrency" for widget in app.slider)
        if access_mode == "public-demo":
            assert next(widget for widget in app.radio if widget.label == "Evaluation target").options == [
                "Synthetic demonstration"
            ]
        app.selectbox(key="advanced_tool").set_value("Settings / Export").run(timeout=30)
        assert not app.exception
        assert any(widget.value == "Export and workspace settings" for widget in app.title)
        visible_notices = " ".join(item.value for item in [*app.info, *app.caption])
        if access_mode == "public-demo":
            assert "server restart" in visible_notices
            assert "tab's memory" not in visible_notices
        elif access_mode == "browser":
            assert "tab's memory" in visible_notices
            assert "reloading" in visible_notices
            assert "inactivity" in visible_notices
    finally:
        if "_studio_private_session" in app.session_state:
            app.session_state["_studio_private_session"].close()
        database.set_repository(None)
