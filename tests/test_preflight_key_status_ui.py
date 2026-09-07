"""Configured provider inputs must not imply access verification or authorize calls."""

import socket

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database


@pytest.fixture
def private_app(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "public-session")
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    network_attempts = []

    def no_network(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError("Configuring a key or preflight must not contact a provider")

    def no_server_key(provider):
        raise AssertionError("Public sessions must not inspect server keys")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(config, "api_key_for_provider", no_server_key)
    database.clear_request()
    app = AppTest.from_file("app.py").run(timeout=30)
    try:
        assert not app.exception
        yield app
        assert not network_attempts
    finally:
        if "_studio_private_session" in app.session_state:
            app.session_state["_studio_private_session"].close()
        database.clear_request()


def metrics(app):
    return {item.label: str(item.value) for item in app.metric}


def widget(items, label):
    return next(item for item in items if item.label == label)


def test_key_presence_is_unverified_and_tracks_selected_provider_and_clear(private_app):
    app = private_app
    app.radio(key="page").set_value("Settings / Export").run(timeout=30)
    assert metrics(app)["API key"] == "Not entered"
    assert metrics(app)["Provider access"] == "Key required"

    widget(app.text_input, "OpenAI API key").set_value("fictional-ui-key-no-provider-access").run(timeout=30)
    assert not app.exception
    assert metrics(app)["API key"] == "Present · unverified"
    assert metrics(app)["Provider access"] == "Not verified"
    assert any("No test request is sent automatically" in item.value for item in app.caption)
    second_key = "fictional-ui-key-second-edit"
    widget(app.text_input, "OpenAI API key").set_value(second_key).run(timeout=30)
    assert widget(app.text_input, "OpenAI API key").value == second_key
    assert app.session_state["provider_api_keys"]["openai"] == second_key
    app.run(timeout=30)
    assert widget(app.text_input, "OpenAI API key").value == second_key
    assert app.session_state["provider_api_keys"]["openai"] == second_key

    widget(app.selectbox, "Provider").set_value("Google Gemini").run(timeout=30)
    assert metrics(app)["API key"] == "Not entered"
    assert metrics(app)["Provider access"] == "Key required"
    gemini_key = "fictional-gemini-ui-key"
    widget(app.text_input, "Google Gemini API key").set_value(gemini_key).run(timeout=30)
    widget(app.selectbox, "Provider").set_value("OpenAI").run(timeout=30)
    assert (widget(app.selectbox, "Provider").value, app.session_state["api_provider"]) == ("OpenAI", "OpenAI")
    assert metrics(app)["Provider access"] == "Not verified"
    assert widget(app.text_input, "OpenAI API key").value == second_key

    widget(app.selectbox, "Provider").set_value("Google Gemini").run(timeout=30)
    app.radio(key="page").set_value("Overview").run(timeout=30)
    assert app.session_state["api_provider"] == "Google Gemini"
    app.radio(key="page").set_value("Settings / Export").run(timeout=30)
    assert widget(app.selectbox, "Provider").value == "Google Gemini"
    assert widget(app.text_input, "Google Gemini API key").value == gemini_key
    assert metrics(app)["Provider access"] == "Not verified"
    widget(app.selectbox, "Provider").set_value("OpenAI").run(timeout=30)
    assert widget(app.text_input, "OpenAI API key").value == second_key
    widget(app.button, "Clear in-app API key").click().run(timeout=30)
    assert not app.exception
    assert widget(app.text_input, "OpenAI API key").value == ""
    assert app.session_state["_provider_key_input_openai"] == ""
    assert metrics(app)["API key"] == "Not entered"
    assert metrics(app)["Provider access"] == "Key required"
    assert not app.session_state["provider_api_keys"]["openai"]
    assert app.session_state["provider_api_keys"]["gemini"] == gemini_key


def test_live_preflight_updates_planned_work_and_never_runs_without_consent(private_app):
    app = private_app
    app.button(key="start_sample").click().run(timeout=30)
    app.session_state["eval_df"] = app.session_state["eval_df"].head(2).copy()
    app.radio(key="page").set_value("Settings / Export").run(timeout=30)
    widget(app.text_input, "OpenAI API key").set_value("fictional-ui-key-no-provider-access").run(timeout=30)
    app.radio(key="page").set_value("Evaluate live assistant").run(timeout=30)
    app.radio(key="live_step").set_value("3. Connect and run").run(timeout=30)
    assert not app.exception
    assert any("key and model access have not been verified" in item.value for item in app.info)
    assert any("2 planned evaluations · 1 candidate(s)" in item.value for item in app.info)
    assert any("unknown; no spending cap is enforced" in item.value for item in app.info)
    assert widget(app.button, "Run Evaluation").disabled

    widget(app.radio, "Evaluation mode").set_value("Current Prompt vs Improved Prompt").run(timeout=30)
    widget(app.slider, "Concurrency").set_value(3)
    widget(app.slider, "Retryable-error retries").set_value(0).run(timeout=30)
    assert any("4 planned evaluations · 2 candidate(s)" in item.value for item in app.info)
    assert any("Up to 3 evaluations at once · up to 0 retries" in item.value for item in app.caption)
    assert any("cached answers may avoid them" in item.value for item in app.caption)
    assert widget(app.button, "Run Evaluation").disabled

    consent = next(item for item in app.checkbox if item.label.startswith("I authorize sending these questions"))
    consent.check().run(timeout=30)
    assert not app.exception
    assert not widget(app.button, "Run Evaluation").disabled
    assert app.session_state["last_results"].empty
    consent = next(item for item in app.checkbox if item.label.startswith("I authorize sending these questions"))
    consent.uncheck().run(timeout=30)
    assert widget(app.button, "Run Evaluation").disabled
