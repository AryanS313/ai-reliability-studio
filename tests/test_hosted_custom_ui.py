"""The hosted customer journey stays in the website and in its own session.

Transport is stubbed; these are workflow checks, not claims of live-provider QA.
"""

from __future__ import annotations

import json
import socket
import sqlite3
from io import BytesIO

import pandas as pd
import pytest
import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.testing.v1 import AppTest

from src import config, database
from src.domain import ExecutionStatus, TargetResponse
from src.targets import ExternalHTTPTarget


def widget(items, label):
    return next(item for item in items if item.label == label)


def page(app, name):
    app.radio(key="navigation").set_value(name).run(timeout=30)
    assert not app.exception


def create_project(app, name="Hosted release"):
    widget(app.button, "Start a project").click().run(timeout=30)
    assert not app.text_input
    assert not app.get("file_uploader")
    app.checkbox(key="privacy_acknowledgement_control").check().run(timeout=30)
    widget(app.text_input, "Project name").set_value(name)
    widget(app.button, "Create project").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["project_id"] is not None


@pytest.fixture
def hosted_ui(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "hosted-session")
    monkeypatch.setattr(config, "AUTH_MODE", "public-session")
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    shared = tmp_path / "must-not-open.sqlite3"
    monkeypatch.setattr(config, "DATABASE_PATH", shared)
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{shared}")

    def fail_network(*args, **kwargs):
        raise AssertionError("Hosted UI fixtures must not use the network")

    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket, "getaddrinfo", fail_network)
    monkeypatch.setenv("OPENAI_API_KEY", "fictional-server-secret-must-not-be-used")
    monkeypatch.setattr(st, "secrets", {"OPENAI_API_KEY": "fictional-streamlit-secret-must-not-be-used"})
    monkeypatch.setattr(config, "OPENAI_API_KEY", "fictional-config-secret-must-not-be-used")
    monkeypatch.setattr(config, "PROVIDER_API_KEYS", {"openai": "fictional-owner-key-must-not-be-used"})
    database.clear_request()
    apps = []

    def create():
        app = AppTest.from_file(config.ROOT_DIR / "app.py").run(timeout=30)
        assert not app.exception
        apps.append(app)
        return app

    yield create
    for app in apps:
        if "_studio_private_session" in app.session_state:
            app.session_state["_studio_private_session"].close()
    database.clear_request()
    assert not shared.exists()


def upload_fixtures(monkeypatch, *, sources=None, questions=None, extra=None):
    original_uploader = st.file_uploader
    extra = extra or {}

    def file(name, content):
        value = BytesIO(content)
        value.name = name
        return value

    def uploaded(label, *args, **kwargs):
        if label in extra:
            return extra[label]
        if label == "Upload knowledge-base documents" and sources is not None:
            return [file(name, content) for name, content in sources]
        if label == "Upload evaluation dataset" and questions is not None:
            return file("questions.json", json.dumps(questions).encode())
        return original_uploader(label, *args, **kwargs)

    monkeypatch.setattr(st, "file_uploader", uploaded)
    monkeypatch.setattr(DeltaGenerator, "file_uploader", lambda self, *args, **kwargs: uploaded(*args, **kwargs))


def prepare_inputs(app, monkeypatch):
    questions = [
        {
            "case_id": "refund-window",
            "question": "How long do I have to request a refund?",
            "expected_answer": "Request a refund within 30 days.",
            "expected_source": "policy.md",
            "category": "Policy",
            "should_escalate": False,
        }
    ]
    upload_fixtures(
        monkeypatch,
        sources=[("policy.md", b"Request a refund within 30 days. Cite this refund policy.")],
        questions=questions,
    )
    widget(app.button, "Continue to sources").click().run(timeout=30)
    widget(app.button, "Index uploaded documents").click().run(timeout=30)
    assert not app.exception
    assert len(app.session_state["documents"]) == 1
    widget(app.button, "Index uploaded documents").click().run(timeout=30)
    assert len(app.session_state["documents"]) == 1
    assert any("duplicate skipped" in item.value for item in app.info)
    widget(app.button, "Continue to cases").click().run(timeout=30)
    assert not app.exception
    assert len(app.session_state["eval_df"]) == 1
    widget(app.button, "Continue to prompt").click().run(timeout=30)
    assert not app.exception
    return questions


def test_hosted_visit_provider_keys_and_second_session_are_separate(hosted_ui):
    first = hosted_ui()
    assert any(button.label == "Start a project" for button in first.button)
    assert any("Private hosted session" in caption.value for caption in first.caption)
    assert not first.code
    visible = " ".join(item.value for item in [*first.caption, *first.info, *first.markdown])
    assert "local workspace" not in visible.lower()
    assert "Authenticated workspace" not in visible
    create_project(first)
    page(first, "Connect")
    widget(first.radio, "What are you testing?").set_value("Direct foundation model").run(timeout=30)
    assert widget(first.text_input, "OpenAI API key").value == ""
    assert any("Add your provider key before running" in item.value for item in first.info)
    widget(first.text_input, "OpenAI API key").set_value("fictional-session-key").run(timeout=30)
    assert first.session_state["provider_api_keys"]["openai"] == "fictional-session-key"
    assert any("validity will be checked" in item.value for item in first.success)
    second = hosted_ui()
    assert second.session_state["project_id"] is None
    assert not second.session_state["privacy_acknowledged"]
    assert second.session_state["provider_api_keys"]["openai"] == ""
    assert (
        second.session_state["_studio_private_session"].repository.list_projects(
            second.session_state["workspace_context"]
        )
        == []
    )
    original = first.session_state["_studio_private_session"]
    widget(first.button, "End session and clear my data").click().run(timeout=30)
    assert not first.exception
    assert original.closed
    assert first.session_state["project_id"] is None
    assert first.session_state["provider_api_keys"]["openai"] == ""
    assert not second.session_state["_studio_private_session"].closed


@pytest.mark.parametrize("access_mode", ["hosted-session", "browser"])
def test_upload_widgets_show_validated_limits_and_preserve_browser_api(hosted_ui, monkeypatch, access_mode):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", access_mode)
    if access_mode == "browser":
        monkeypatch.setattr(config, "APP_ENV", "development")
        monkeypatch.setattr(config, "is_browser_runtime", lambda: True)
        monkeypatch.setattr(config, "browser_runtime_enabled", lambda: True)
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 2 * 1024 * 1024)
    monkeypatch.setattr(config, "MAX_EXTERNAL_REQUEST_BYTES", 1024 * 1024)
    seen = {}
    original_st = st.file_uploader
    original_column = DeltaGenerator.file_uploader

    def inspect_upload(label, *args, **kwargs):
        seen[label] = kwargs.get("max_upload_size")
        if access_mode == "browser":
            assert "max_upload_size" not in kwargs  # Older browser Streamlit rejects this argument.
        return original_st(label, *args, **kwargs)

    def inspect_column(self, label, *args, **kwargs):
        seen[label] = kwargs.get("max_upload_size")
        if access_mode == "browser":
            assert "max_upload_size" not in kwargs
        return original_column(self, label, *args, **kwargs)

    monkeypatch.setattr(st, "file_uploader", inspect_upload)
    monkeypatch.setattr(DeltaGenerator, "file_uploader", inspect_column)
    app = hosted_ui()
    create_project(app)
    widget(app.button, "Continue to sources").click().run(timeout=30)
    assert not app.exception
    source = widget(app.get("file_uploader"), "Upload knowledge-base documents")
    if access_mode == "hosted-session":
        assert source.proto.max_upload_size_mb == 2
    widget(app.button, "Continue to cases").click().run(timeout=30)
    assert not app.exception
    app.selectbox(key="advanced_tool").set_value("Review saved answers").run(timeout=30)
    assert not app.exception
    page(app, "Start")
    widget(app.button, "Resume a project").click().run(timeout=30)
    assert not app.exception
    if access_mode == "hosted-session":
        assert seen["Upload evaluation dataset"] == 2
        assert seen["Source documents"] == 2
        assert seen["Questions and expected answers"] == 2
        assert seen["Saved assistant answers"] == 2
        assert widget(app.get("file_uploader"), "Project download").proto.max_upload_size_mb == 20
    else:
        assert seen and all(limit is None for limit in seen.values())


def test_hosted_custom_https_review_compare_and_export_stay_online(hosted_ui, monkeypatch):
    app = hosted_ui()
    create_project(app)
    prepare_inputs(app, monkeypatch)
    page(app, "Connect")
    assert widget(app.radio, "What are you testing?").value == "External assistant/API"
    widget(app.text_input, "Assistant endpoint").set_value("https://assistant.example.test/answer")
    widget(app.text_input, "Session-only token or key").set_value("fictional-target-credential")
    widget(app.text_input, "Read-only health path (optional)").set_value("/health")
    widget(app.button, "Save connection").click().run(timeout=30)
    assert not app.exception and not app.error
    assert "fictional-target-credential" not in json.dumps(app.session_state["external_target_config"])
    assert widget(app.button, "Check connection").disabled
    calls = []

    def check(target):
        calls.append("health")
        return TargetResponse(ExecutionStatus.PASSED, metadata={"network_checked": True})

    def execute(target, request):
        calls.append("answer")
        return TargetResponse(
            ExecutionStatus.PASSED,
            answer="Request a refund within 30 days. Source: policy.md",
            citations=({"source_name": "policy.md"},),
            model="fixture-observed-model",
            latency_ms=25.0,
            cost=0.001,
        )

    monkeypatch.setattr(ExternalHTTPTarget, "health_check", check)
    monkeypatch.setattr(ExternalHTTPTarget, "execute", execute)
    next(item for item in app.checkbox if item.label.startswith("I authorize one connection")).check().run(timeout=30)
    widget(app.button, "Check connection").click().run(timeout=30)
    assert calls == ["health"]
    assert any("connectivity only" in item.value for item in app.success)
    page(app, "Evaluate")
    assert widget(app.radio, "Evaluation target").value == "External assistant/API"
    assert widget(app.button, "Run Evaluation").disabled
    assert widget(app.slider, "Questions running at once").max == 2
    assert widget(app.slider, "Retries after temporary errors").max == 1
    next(item for item in app.checkbox if item.label.startswith("I authorize these external calls")).check().run(
        timeout=30
    )
    widget(app.button, "Run Evaluation").click().run(timeout=30)
    assert not app.exception
    assert calls == ["health", "answer"]
    first_run = app.session_state["last_results"]
    assert len(first_run) == 1 and first_run["target_type"].eq("external_api").all()
    assert first_run["execution_status"].eq("passed").all()
    assert any(button.label == "Check agreement with human reviewers" for button in app.button)
    widget(app.button, "Check agreement with human reviewers").click().run(timeout=30)
    assert not app.exception
    assert any(item.label == "Validate and save calibration result" for item in app.button)
    assert any("insufficient" in item.value.lower() for item in app.warning)
    page(app, "Evaluate")
    next(item for item in app.checkbox if item.label.startswith("I authorize these external calls")).check().run(
        timeout=30
    )
    widget(app.button, "Run Evaluation").click().run(timeout=30)
    assert not app.exception
    page(app, "History")
    assert not widget(app.button, "Compare selected runs").disabled
    widget(app.button, "Compare selected runs").click().run(timeout=30)
    assert not app.exception
    page(app, "Review")
    app.radio(key="review_view").set_value("Export evidence").run(timeout=30)
    assert not app.exception
    assert any(item.label == "Download readable report" for item in app.get("download_button"))
    assert not app.get("json")
    repository = app.session_state["_studio_private_session"].repository
    context = app.session_state["workspace_context"]
    runs = repository.list_runs(context)
    assert len(runs) == 2
    assert all(run["project_id"] == app.session_state["project_id"] for run in runs)


def test_hosted_sample_preserves_simulated_errors_and_full_case_count(hosted_ui):
    app = hosted_ui()
    widget(app.button, "Try the sample review").click().run(timeout=30)
    assert not app.exception
    results = app.session_state["last_results"]
    assert len(results) == 32
    assert results["target_type"].eq("synthetic_mock").all()
    assert results["manifest"].map(lambda value: value["target"]["execution_policy"]["max_concurrency"]).eq(2).all()
    assert any("simulated connection failures" in item.value for item in app.error)
    assert any("no launch verdict" in item.value for item in app.warning)


def test_hosted_storage_capacity_has_recovery_instead_of_a_traceback(hosted_ui, monkeypatch):
    app = hosted_ui()
    widget(app.button, "Start a project").click().run(timeout=30)
    app.checkbox(key="privacy_acknowledgement_control").check().run(timeout=30)
    widget(app.text_input, "Project name").set_value("Capacity fixture")

    def full(*args, **kwargs):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(database, "save_project", full)
    widget(app.button, "Create project").click().run(timeout=30)
    assert not app.exception
    assert any("storage limit" in item.value and "Download your project" in item.value for item in app.error)
    assert any(item.label == "Open saved projects and downloads" for item in app.button)
    assert app.session_state["project_id"] is None


def test_hosted_oversized_review_is_explained_before_any_execution(hosted_ui, monkeypatch):
    app = hosted_ui()
    create_project(app)
    questions = prepare_inputs(app, monkeypatch)
    app.session_state["eval_df"] = pd.DataFrame([{**questions[0], "case_id": f"case-{index}"} for index in range(101)])
    app.session_state["target_kind"] = "Direct foundation model"
    app.session_state["provider_api_keys"]["openai"] = "fictional-explicit-key"
    page(app, "Evaluate")
    assert any("101 answers" in item.value and "100 per review" in item.value for item in app.error)
    next(item for item in app.checkbox if item.label.startswith("I authorize these external calls")).check().run(
        timeout=30
    )
    assert widget(app.button, "Run Evaluation").disabled
    assert app.session_state["last_results"].empty


def test_project_download_resumes_into_separate_session_without_credentials(hosted_ui, monkeypatch):
    from src.project_workspace import export_project_workspace

    first = hosted_ui()
    create_project(first)
    prepare_inputs(first, monkeypatch)
    first.session_state["provider_api_keys"]["openai"] = "fictional-export-excluded-key"
    first_id = first.session_state["project_id"]
    first_session = first.session_state["_studio_private_session"]
    content = export_project_workspace(first_session.repository, first_session.context, first_id)
    assert b"fictional-export-excluded-key" not in content
    page(first, "Start")
    assert any(item.label == "Download project to resume later" for item in first.get("download_button"))

    second = hosted_ui()
    widget(second.button, "Resume a project").click().run(timeout=30)
    assert second.session_state["project_id"] is None
    second.checkbox(key="privacy_acknowledgement_control").check().run(timeout=30)
    uploaded = BytesIO(content)
    uploaded.name = "reliability-project.json"
    upload_fixtures(monkeypatch, extra={"Project download": uploaded})
    second.run(timeout=30)
    widget(second.button, "Restore project").click().run(timeout=30)
    assert not second.exception and not second.error
    assert second.session_state["project_id"] is not None
    assert len(second.session_state["documents"]) == 1
    assert len(second.session_state["eval_df"]) == 1
    assert not any(second.session_state["provider_api_keys"].values())
    assert second.session_state["external_target_secret"] == ""
    assert first.session_state["provider_api_keys"]["openai"] == "fictional-export-excluded-key"
    assert first_session.repository.list_projects(first_session.context)[0]["id"] == first_id

    page(second, "Start")
    previous_project = second.session_state["project_id"]
    invalid = BytesIO(b'{"unsupported":true}')
    invalid.name = "invalid-project.json"
    upload_fixtures(monkeypatch, extra={"Project download": invalid})
    widget(second.button, "Resume a project").click().run(timeout=30)
    widget(second.button, "Restore project").click().run(timeout=30)
    assert not second.exception
    assert any("could not be restored" in item.value for item in second.error)
    assert second.session_state["project_id"] == previous_project
    assert len(second.session_state["eval_df"]) == 1
