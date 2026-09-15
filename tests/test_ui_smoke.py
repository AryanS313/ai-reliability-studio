from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.storage import SQLiteRepository


def app_for(monkeypatch, repository, *, project=False):
    database.set_repository(repository)
    # AppTest starts a separate thread; ContextVar bindings intentionally do not transfer.
    monkeypatch.setattr(database, "repository_from_url", lambda: repository)
    app = AppTest.from_file(config.ROOT_DIR / "app.py")
    if project:
        context = repository.local_context()
        project_id = repository.create_project(context, {"name": "Support review"})
        app.session_state["project_id"] = project_id
        app.session_state["project"] = {"name": "Support review"}
        app.session_state["privacy_acknowledged"] = True
    return app.run(timeout=30)


def test_streamlit_one_click_sample_has_no_launch_verdict_and_preserves_all_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "public-demo")
    app = app_for(monkeypatch, SQLiteRepository(tmp_path / "untouched.sqlite3"))
    assert not app.exception
    assert app.radio(key="navigation").options == ["Start", "Prepare", "Connect", "Evaluate", "Review", "History"]
    assert not app.get("file_uploader")
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert app.session_state["navigation"] == "Review"
    frame = app.session_state["last_results"]
    assert len(frame) == 32
    assert len(app.session_state["chunks"]) == 30
    assert frame["target_type"].eq("synthetic_mock").all()
    assert any("no launch verdict" in item.value for item in app.warning)
    assert app.session_state["sample_duration_ms"] < 10_000
    assert not (tmp_path / "untouched.sqlite3").exists()


def test_user_journey_has_plain_checks_without_inline_json_or_version_columns(tmp_path, monkeypatch):
    app = app_for(monkeypatch, SQLiteRepository(tmp_path / "plain-language.sqlite3"))
    app.button[0].click().run(timeout=30)
    app.session_state["privacy_acknowledged"] = True
    assert not app.get("json")
    rendered_checks = " ".join(item.value for item in app.markdown)
    assert "Evidence from a real assistant — Not met" in rendered_checks
    assert "Sample answers demonstrate the workflow" in rendered_checks
    # Explanations wrap as text instead of being clipped in a horizontally scrolling grid.
    assert not any("What it means" in table.value.columns for table in app.dataframe)
    assert not any(
        column in table.value.columns
        for table in app.dataframe
        for column in ["actual", "threshold", "candidate_id", "prompt_version"]
    )
    for view in ["Inspect failures", "Export evidence"]:
        app.radio(key="review_view").set_value(view).run(timeout=30)
        assert not app.exception
        assert not app.get("json")
    for page in ["Prepare", "Connect", "History"]:
        app.radio(key="navigation").set_value(page).run(timeout=30)
        assert not app.exception
        assert not app.get("json")
        assert not any("JSON" in area.label for area in app.text_area)
    app.selectbox(key="advanced_tool").set_value("Evaluator Calibration").run(timeout=30)
    assert not app.exception
    assert not app.get("json")


def test_review_export_is_redacted_and_audited(tmp_path, monkeypatch):
    repository = SQLiteRepository(tmp_path / "exports.sqlite3")
    app = app_for(monkeypatch, repository)
    app.button[0].click().run(timeout=30)
    app.radio(key="review_view").set_value("Export evidence").run(timeout=30)
    assert not app.exception
    assert len(app.get("download_button")) == 3
    assert any("redacted" in item.value.lower() for item in app.caption)
    frame = app.session_state["last_results"]
    from src.reporting import json_report

    payload = json_report(frame, redact_personal_data=True)
    assert "4111111111111111" not in payload
    assert "Synthetic demonstration" in payload
    database.record_export("json", payload, int(frame.iloc[0]["run_id"]), context=repository.local_context())
    with repository.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'report.export'").fetchone()[0] == 1


def test_calibration_empty_state_and_clear_recovery(tmp_path, monkeypatch):
    app = app_for(monkeypatch, SQLiteRepository(tmp_path / "calibration.sqlite3"), project=True)
    app.selectbox(key="advanced_tool").set_value("Evaluator Calibration").run(timeout=30)
    assert not app.exception
    rendered = " ".join(item.value for item in [*app.markdown, *app.warning, *app.info, *app.caption])
    assert "held-out" in rendered.lower()
    assert "insufficient" in rendered.lower()
    assert "statistical confidence" in rendered.lower()
    assert any(item.label == "Validate and save calibration result" for item in app.button)


def test_dataset_coverage_surfaces_thin_categories_without_a_quality_verdict(tmp_path, monkeypatch):
    app = app_for(monkeypatch, SQLiteRepository(tmp_path / "coverage.sqlite3"), project=True)
    app.selectbox(key="advanced_tool").set_value("Evaluation Dataset").run(timeout=30)
    next(item for item in app.button if item.label == "Load sample evaluation dataset").click().run(timeout=30)
    assert not app.exception
    assert any("fewer than 5" in item.value for item in app.warning)
    assert any("does not establish assistant quality" in item.value for item in app.caption)
    assert not any("launch-evidence" in item.value for item in app.success)


def test_missing_external_session_credential_blocks_preflight_without_network(tmp_path, monkeypatch):
    app = app_for(monkeypatch, SQLiteRepository(tmp_path / "missing-external-key.sqlite3"))
    app.button[0].click().run(timeout=30)
    app.session_state["privacy_acknowledged"] = True
    app.session_state["target_kind"] = "External assistant/API"
    app.session_state["external_target_config"] = {
        "name": "Fixture assistant",
        "endpoint": "https://assistant.example.com/answer",
        "headers": {"Authorization": "secret://SESSION_EXTERNAL_AUTH"},
    }

    def unexpected_network(*args, **kwargs):
        raise AssertionError("Preflight must not perform network requests")

    monkeypatch.setattr("socket.getaddrinfo", unexpected_network)
    app.radio(key="navigation").set_value("Evaluate").run(timeout=30)
    assert not app.exception
    assert any("session credential" in item.value for item in app.error)
    assert next(item for item in app.button if item.label == "Run Evaluation").disabled


def test_public_advanced_tools_do_not_expose_custom_upload_or_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "public-demo")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "host-key-never-shown")
    app = app_for(monkeypatch, SQLiteRepository(tmp_path / "private.sqlite3"))
    for page in ["Prepare", "Connect", "Evaluate"]:
        app.radio(key="navigation").set_value(page).run(timeout=30)
        assert not app.exception
        assert not app.get("file_uploader")
        assert not app.text_input
    app.selectbox(key="advanced_tool").set_value("Settings / Export").run(timeout=30)
    rendered = " ".join(item.value for item in [*app.markdown, *app.warning, *app.info, *app.caption])
    assert "host-key-never-shown" not in rendered
    assert not app.text_input


def test_privacy_ack_survives_navigation_and_project_creation(tmp_path, monkeypatch):
    app = app_for(monkeypatch, SQLiteRepository(tmp_path / "privacy.sqlite3"))
    next(item for item in app.button if item.label == "Start a project").click().run(timeout=30)
    app.checkbox[0].check().run(timeout=30)
    app.text_input[0].set_value("September support release")
    next(item for item in app.button if item.label == "Create project").click().run(timeout=30)
    assert app.session_state["project_id"]
    assert app.session_state["privacy_acknowledged"] is True
    next(item for item in app.button if item.label == "Continue to sources").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["prepare_step"] == "2 · Sources"
    assert app.get("file_uploader")
    app.radio(key="navigation").set_value("Connect").run(timeout=30)
    assert not app.exception
    assert app.session_state["privacy_acknowledged"] is True
    assert any(item.label == "Assistant endpoint" for item in app.text_input)


def test_analytics_does_not_repeat_sample_events_on_result_rerun(tmp_path, monkeypatch):
    repository = SQLiteRepository(tmp_path / "events.sqlite3")
    app = app_for(monkeypatch, repository)
    app.button[0].click().run(timeout=30)
    app.run(timeout=30)
    with repository.connection() as conn:
        rows = conn.execute("SELECT action, metadata_json FROM audit_logs WHERE action LIKE 'product.%'").fetchall()
    actions = [row["action"] for row in rows]
    assert actions.count("product.sample_loaded") == 1
    assert actions.count("product.report_viewed") == 1
    assert all("question" not in json.loads(row["metadata_json"]) for row in rows)


@pytest.mark.parametrize("target_kind", ["Direct foundation model", "External assistant/API"])
def test_sample_does_not_authorize_real_execution_without_privacy_ack(tmp_path, monkeypatch, target_kind):
    app = app_for(monkeypatch, SQLiteRepository(tmp_path / "sample-to-real.sqlite3"))
    next(item for item in app.button if item.label == "Try the sample review").click().run(timeout=30)
    assert app.session_state["mode"] == "Demo Mode"
    assert app.session_state["privacy_acknowledged"] is False
    assert len(app.session_state["last_results"]) == 32
    app.radio(key="navigation").set_value("Evaluate").run(timeout=30)
    assert any(item.label == "Run Evaluation" for item in app.button)

    # A completed sample grants no permission to send data to a provider or API.
    calls = []
    monkeypatch.setattr("src.evaluator.run_evaluation", lambda *args, **kwargs: calls.append(kwargs))
    app.radio(key="_evaluation_target").set_value(target_kind).run(timeout=30)
    assert not app.exception
    assert app.session_state["privacy_acknowledged"] is False
    assert not any(item.label == "Run Evaluation" for item in app.button)
    assert app.checkbox(key="privacy_acknowledgement_control")
    assert not calls

    app.checkbox(key="privacy_acknowledgement_control").check().run(timeout=30)
    assert not app.exception
    assert app.session_state["privacy_acknowledged"] is True
    assert any(item.label == "Run Evaluation" for item in app.button)
    assert not calls
