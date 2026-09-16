"""Configured provider inputs must not imply verification or authorize calls."""

import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.storage import SQLiteRepository


@pytest.fixture
def private_app(monkeypatch, tmp_path, request):
    access_mode = getattr(request, "param", "browser")
    monkeypatch.setattr(config, "APP_ACCESS_MODE", access_mode)
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    monkeypatch.setattr(config, "is_browser_runtime", lambda: access_mode == "browser")
    monkeypatch.setattr(config, "browser_runtime_enabled", lambda: access_mode == "browser")
    network_attempts = []

    def no_network(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError("Configuring a key or preflight must not contact a provider")

    def server_key(provider):
        if access_mode == "browser":
            raise AssertionError("Browser sessions must not inspect server keys")
        return ""

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(config, "api_key_for_provider", server_key)
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda path: False if path.name in {"secrets.toml", ".env"} else original_is_file(path),
    )
    repository = SQLiteRepository(tmp_path / "key-status.sqlite3")
    monkeypatch.setattr(database, "repository_from_url", lambda: repository)
    database.set_repository(repository)
    app = AppTest.from_file(str(config.ROOT_DIR / "app.py")).run(timeout=30)
    try:
        assert not app.exception
        # The authored fixture saves a project and loads approved fictional inputs.
        app.button(key="start_saved_sample").click().run(timeout=30)
        app.selectbox(key="advanced_tool").set_value("Settings / Export").run(timeout=30)
        assert not any(item.label.endswith("API key") for item in app.text_input)
        app.checkbox(key="privacy_acknowledgement_control").check().run(timeout=30)
        assert not app.exception
        assert app.session_state["project_id"] is not None
        assert app.session_state["privacy_acknowledged"]
        yield app
        assert not network_attempts
    finally:
        if "_studio_private_session" in app.session_state:
            app.session_state["_studio_private_session"].close()
        database.set_repository(None)


def widget(items, label):
    return next(item for item in items if item.label == label)


def assert_key_status(app, *, present):
    assert not app.exception
    if present:
        assert any("validity will be checked by the first provider request" in item.value for item in app.success)
    else:
        assert any("Add your provider key before running" in item.value for item in app.info)
    assert not any("verified" == str(item.value).lower() for item in app.metric)


def test_key_presence_is_unverified_and_tracks_selected_provider_and_clear(private_app):
    app = private_app
    assert_key_status(app, present=False)
    widget(app.text_input, "OpenAI API key").set_value("fictional-ui-key-no-provider-access").run(timeout=30)
    assert_key_status(app, present=True)
    second_key = "fictional-ui-key-second-edit"
    widget(app.text_input, "OpenAI API key").set_value(second_key).run(timeout=30)
    assert widget(app.text_input, "OpenAI API key").value == second_key
    assert app.session_state["provider_api_keys"]["openai"] == second_key
    app.run(timeout=30)
    assert widget(app.text_input, "OpenAI API key").value == second_key
    assert app.session_state["provider_api_keys"]["openai"] == second_key

    widget(app.selectbox, "Provider").set_value("Google Gemini").run(timeout=30)
    assert_key_status(app, present=False)
    gemini_key = "fictional-gemini-ui-key"
    widget(app.text_input, "Google Gemini API key").set_value(gemini_key).run(timeout=30)
    widget(app.selectbox, "Provider").set_value("OpenAI").run(timeout=30)
    assert (widget(app.selectbox, "Provider").value, app.session_state["api_provider"]) == ("OpenAI", "OpenAI")
    assert_key_status(app, present=True)
    assert widget(app.text_input, "OpenAI API key").value == second_key

    widget(app.selectbox, "Provider").set_value("Google Gemini").run(timeout=30)
    app.radio(key="navigation").set_value("Start").run(timeout=30)
    assert app.session_state["api_provider"] == "Google Gemini"
    app.selectbox(key="advanced_tool").set_value("Settings / Export").run(timeout=30)
    assert widget(app.selectbox, "Provider").value == "Google Gemini"
    assert widget(app.text_input, "Google Gemini API key").value == gemini_key
    assert_key_status(app, present=True)
    widget(app.selectbox, "Provider").set_value("OpenAI").run(timeout=30)
    assert widget(app.text_input, "OpenAI API key").value == second_key
    widget(app.button, "Clear session key").click().run(timeout=30)
    assert not app.exception
    assert widget(app.text_input, "OpenAI API key").value == ""
    assert app.session_state["provider_secret_openai"] == ""
    assert_key_status(app, present=False)
    assert not app.session_state["provider_api_keys"]["openai"]
    assert app.session_state["provider_api_keys"]["gemini"] == gemini_key


@pytest.mark.parametrize("private_app", ["browser", "local"], indirect=True)
def test_live_preflight_updates_planned_work_and_never_runs_without_consent(private_app):
    app = private_app
    app.session_state["eval_df"] = app.session_state["eval_df"].head(2).copy()
    widget(app.text_input, "OpenAI API key").set_value("fictional-ui-key-no-provider-access").run(timeout=30)
    assert_key_status(app, present=True)
    app.selectbox(key="advanced_tool").set_value("Evaluate live assistant").run(timeout=30)
    app.radio(key="live_step").set_value("3. Connect and run").run(timeout=30)
    assert not app.exception
    widget(app.radio, "Evaluation target").set_value("Direct foundation model").run(timeout=30)
    assert not app.exception
    assert any("2 planned executions" in item.value and "1 candidate(s)" in item.value for item in app.info)
    assert any("unknown until exact token usage is returned" in item.value for item in app.info)
    assert widget(app.button, "Run Evaluation").disabled

    widget(app.radio, "What would you like to check?").set_value("Current Prompt vs Improved Prompt").run(timeout=30)
    if config.is_browser_runtime():
        assert not any(item.label == "Questions running at once" for item in app.slider)
        assert any("One question runs at a time" in item.value for item in app.caption)
    else:
        widget(app.slider, "Questions running at once").set_value(3)
    widget(app.slider, "Retries after temporary errors").set_value(1).run(timeout=30)
    assert any(
        "4 planned executions" in item.value and "8 attempts" in item.value and "2 candidate(s)" in item.value
        for item in app.info
    )
    assert widget(app.button, "Run Evaluation").disabled
    consent = next(item for item in app.checkbox if item.label.startswith("I authorize these external calls"))
    consent.check().run(timeout=30)
    assert not app.exception
    assert not widget(app.button, "Run Evaluation").disabled
    assert app.session_state["last_results"].empty

    # Consent is bound to the displayed plan, including retry count and credential.
    widget(app.slider, "Retries after temporary errors").set_value(0).run(timeout=30)
    assert widget(app.button, "Run Evaluation").disabled
    assert any("at most 4 attempts" in item.value for item in app.info)
    consent = next(item for item in app.checkbox if item.label.startswith("I authorize these external calls"))
    consent.check().run(timeout=30)
    assert not widget(app.button, "Run Evaluation").disabled
    consent = next(item for item in app.checkbox if item.label.startswith("I authorize these external calls"))
    consent.uncheck().run(timeout=30)
    assert widget(app.button, "Run Evaluation").disabled
    assert app.session_state["last_results"].empty
