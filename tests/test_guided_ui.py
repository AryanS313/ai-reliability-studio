from __future__ import annotations

import json
import socket
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.saved_responses import compare_response_reviews
from src.ui_workflows import evaluate_review_workspace, read_review_workspace, sample_review_workspace


@pytest.fixture
def private_ui(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "public-session")
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "PUBLIC_SESSION_TTL_SECONDS", 3600)
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())

    def no_network(*args, **kwargs):
        raise AssertionError("Guided UI checks must not contact a provider or the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path, "is_file", lambda path: False if path.name in {"secrets.toml", ".env"} else original_is_file(path)
    )
    database.clear_request()
    apps = []

    def create():
        app = AppTest.from_file("app.py").run(timeout=30)
        assert not app.exception
        apps.append(app)
        return app

    yield create
    for app in apps:
        if "_studio_private_session" in app.session_state:
            app.session_state["_studio_private_session"].close()
    database.clear_request()


def save_visible_review(app, decision, note):
    next(widget for widget in app.selectbox if widget.label == "Decision").set_value(decision)
    next(widget for widget in app.text_area if widget.label == "What in the source supports your decision?").set_value(
        note
    )
    next(widget for widget in app.text_input if widget.label == "Reviewer name").set_value("UI test reviewer")
    next(widget for widget in app.selectbox if widget.label == "Review method").set_value("Reviewed with AI assistance")
    next(widget for widget in app.checkbox if widget.label.startswith("I checked this answer")).check()
    next(widget for widget in app.button if widget.label == "Save review and continue").click().run(timeout=30)
    assert not app.exception


def test_sample_can_be_reviewed_and_retested_without_provider_calls(private_ui):
    app = private_ui()
    assert {"Try sample", "Review saved answers", "Evaluate live assistant"}.issubset(
        {button.label for button in app.button}
    )
    app.button(key="start_sample").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["offline_baseline"]["review_status"].eq("pending").all()
    assert app.session_state["offline_baseline"]["review_decision"].isna().all()
    next(button for button in app.button if button.label == "Save review and continue").click().run(timeout=30)
    assert app.session_state["offline_baseline"]["review_status"].eq("pending").all()
    assert any("Choose a decision" in warning.value for warning in app.warning)
    save_visible_review(
        app, "Supported by the sources", "The export passage states 24 hours, matching the answer and its citation."
    )
    assert (
        next(widget for widget in app.text_area if widget.label == "What in the source supports your decision?").value
        == ""
    )
    next(widget for widget in app.selectbox if widget.label == "Decision").set_value("Needs a fix")
    next(widget for widget in app.checkbox if widget.label.startswith("I checked this answer")).check()
    next(button for button in app.button if button.label == "Save review and continue").click().run(timeout=30)
    assert app.session_state["offline_baseline"]["review_status"].eq("reviewed").sum() == 1
    assert any("Choose a decision" in warning.value for warning in app.warning)
    save_visible_review(app, "Needs a fix", "The answer states 48 hours while the export passage states 24 hours.")
    assert any("Expected routing: security · high" in caption.value for caption in app.caption)
    assert any("Returned action: escalate to operations; urgency normal." in text.value for text in app.markdown)
    save_visible_review(
        app,
        "Needs a fix",
        "The returned action uses operations and normal urgency; the source requires security and high.",
    )
    baseline = app.session_state["offline_baseline"]
    assert baseline["review_status"].eq("reviewed").all()
    assert baseline["reviewer_kind"].eq("ai_assisted").all()
    assert baseline["review_decision"].tolist() == ["supported", "failed", "failed"]
    app.button(key="sample_replacements").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["offline_candidate"]["review_status"].eq("pending").all()
    pending_comparison = compare_response_reviews(baseline, app.session_state["offline_candidate"])
    assert pending_comparison["counts"] == {"pending_review": 2}
    save_visible_review(
        app, "Supported by the sources", "The replacement now states the 24-hour limit in the export passage."
    )
    save_visible_review(
        app, "Supported by the sources", "The replacement action now uses security with high urgency as required."
    )
    comparison = compare_response_reviews(baseline, app.session_state["offline_candidate"])
    assert comparison["counts"] == {"resolved": 2}
    assert comparison["baseline_case_count"] == 3 and comparison["candidate_case_count"] == 2
    assert len(app.get("download_button")) >= 5
    exported = json.dumps(app.session_state["offline_workspace"]).encode()
    restored = read_review_workspace(exported)
    restored_baseline = evaluate_review_workspace(restored)
    restored_candidate = evaluate_review_workspace(restored, "candidate")
    assert restored_baseline["review_status"].eq("reviewed").all()
    assert compare_response_reviews(restored_baseline, restored_candidate)["counts"] == {"resolved": 2}


def test_pasted_inputs_import_and_mismatch_is_explained(private_ui):
    app = private_ui()
    app.button(key="start_saved").click().run(timeout=30)
    app.radio(key="saved_input_method").set_value("Paste JSON").run(timeout=30)
    sample = sample_review_workspace()
    app.text_area(key="saved_sources_json").set_value(json.dumps(sample["sources"]))
    app.text_area(key="saved_questions_json").set_value(json.dumps(sample["dataset"]))
    app.text_area(key="saved_answers_json").set_value(json.dumps(sample["baseline"]["responses"][:-1]))
    app.text_input(key="saved_target_name").set_value("Local fixture import")
    app.text_input(key="saved_target_version").set_value("fixture-v1")
    app.text_input(key="saved_captured_at").set_value("2026-01-01T12:00:00+00:00")
    app.checkbox(key="saved_fixture_flag").check()
    next(button for button in app.button if button.label == "Import answers").click().run(timeout=30)
    assert not app.exception
    assert any("couldn't import" in error.value for error in app.error)
    assert any("Case/response sets differ" in item.value for item in app.caption)
    assert "offline_workspace" not in app.session_state
    app.text_area(key="saved_answers_json").set_value(json.dumps(sample["baseline"]["responses"]))
    next(button for button in app.button if button.label == "Import answers").click().run(timeout=30)
    assert not app.exception
    frame = app.session_state["offline_baseline"]
    assert len(frame) == 3 and frame["review_status"].eq("pending").all()
    assert frame["client_retrieval_status"].eq("not_measured").all()
    assert frame["latency_ms"].isna().all() and frame["estimated_cost"].isna().all()


def test_live_path_keeps_existing_tools_and_never_defaults_to_synthetic(private_ui):
    app = private_ui()
    app.button(key="start_live").click().run(timeout=30)
    assert not app.exception
    assert next(button for button in app.button if button.label == "Next: questions").disabled
    app.radio(key="live_step").set_value("3. Connect and run").run(timeout=30)
    assert not app.exception
    target = next(widget for widget in app.radio if widget.label == "Evaluation target")
    assert "Synthetic demonstration" not in target.options
    assert next(button for button in app.button if button.label == "Run Evaluation").disabled
    assert any("External API connections are disabled" in info.value for info in app.info)
    assert {"Evaluator Calibration", "Prompt Comparison", "Run History / Comparison", "Settings / Export"}.issubset(
        set(app.radio(key="page").options)
    )
    app.radio(key="page").set_value("Target Setup").run(timeout=30)
    assert not app.exception
    assert any("External API connections are disabled" in info.value for info in app.info)
    assert not any(button.label == "Check connection" for button in app.button)


def test_public_settings_ignore_server_credentials_and_end_session_clears_ui(private_ui, monkeypatch):
    def forbidden_server_key(provider):
        raise AssertionError("The public UI must not inspect or use server credentials")

    monkeypatch.setattr(config, "api_key_for_provider", forbidden_server_key)
    app = private_ui()
    app.button(key="start_sample").click().run(timeout=30)
    app.radio(key="page").set_value("Settings / Export").run(timeout=30)
    assert not app.exception
    assert any(str(metric.value) == "Disabled for public sessions" for metric in app.metric)
    next(button for button in app.button if button.label == "End session and clear my data").click().run(timeout=30)
    assert not app.exception
    assert "offline_workspace" not in app.session_state
    assert app.session_state["last_results"].empty
    assert all(not value for value in app.session_state["provider_api_keys"].values())


def test_resume_refuses_stale_reviews_and_unknown_replacement_cases():
    sample = sample_review_workspace()
    baseline = evaluate_review_workspace(sample)
    row = baseline.iloc[0].to_dict()
    bad_review = {key: row[key] for key in ("case_id", "response_hash", "case_version", "knowledge_base_version")}
    bad_review.update(
        decision="supported",
        reviewer="Fixture reviewer",
        reviewer_kind="ai_assisted",
        note="Fixture check",
        response_hash="stale",
    )
    sample["baseline"]["reviews"] = [bad_review]
    with pytest.raises(ValueError, match="response_hash"):
        evaluate_review_workspace(read_review_workspace(json.dumps(sample).encode()))
    another = deepcopy(sample_review_workspace())
    another["candidate"] = {
        "responses": [{"case_id": "not-in-original", "actual_answer": "A"}],
        "target_version": "v2",
        "captured_at": "2026-01-01T13:00:00+00:00",
    }
    with pytest.raises(ValueError, match="case IDs"):
        evaluate_review_workspace(another, "candidate")


@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        ("baseline", None),
        ("baseline", []),
        ("dataset", []),
        ("dataset", ["bad"]),
        ("sources", []),
        ("sources", [{}]),
        ("candidate", []),
        ("baseline", {"responses": []}),
    ],
)
def test_resume_rejects_incomplete_workspaces(key, replacement):
    sample = sample_review_workspace()
    sample[key] = replacement
    with pytest.raises(ValueError):
        read_review_workspace(json.dumps(sample).encode())
    with pytest.raises(ValueError):
        evaluate_review_workspace(sample)
