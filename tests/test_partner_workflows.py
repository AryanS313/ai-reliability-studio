from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.chunker import chunk_documents
from src.storage import SQLiteRepository


def _find(elements, label):
    return next(element for element in elements if element.label == label)


def _page(app, page):
    _find(app.radio, "Workflow").set_value(page).run(timeout=30)
    assert not app.exception


def _events(repository):
    with repository.connection() as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM audit_logs WHERE action LIKE 'product.%' ORDER BY id")
        ]


@pytest.fixture
def private_app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "local")
    repository = SQLiteRepository(tmp_path / "partner-workflow.sqlite3")
    database.set_repository(repository)
    app = AppTest.from_file(config.ROOT_DIR / "app.py").run(timeout=30)
    assert not app.exception
    yield app, repository
    database.set_repository(None)


def test_custom_project_requires_privacy_and_nonempty_name_before_asset_controls(private_app):
    app, repository = private_app
    _find(app.button, "Start a project").click().run(timeout=30)
    assert not app.exception
    assert not app.text_input
    assert not app.get("file_uploader")
    assert app.session_state["project_id"] is None
    app.checkbox[0].check().run(timeout=30)
    assert not app.exception
    _find(app.button, "Create project").click().run(timeout=30)
    assert app.error
    assert app.session_state["project_id"] is None
    _find(app.radio, "Preparation step").set_value("2 · Sources").run(timeout=30)
    assert not app.exception
    assert not app.get("file_uploader")
    assert any("Create or reopen a project" in item.value for item in app.info)
    _find(app.button, "Go to project setup").click().run(timeout=30)
    _find(app.text_input, "Project name").set_value("Private fixture project")
    _find(app.button, "Create project").click().run(timeout=30)
    assert not app.exception
    project_id = app.session_state["project_id"]
    assert project_id is not None
    _find(app.button, "Continue to sources").click().run(timeout=30)
    assert not app.exception
    assert len(app.get("file_uploader")) == 1
    events = _events(repository)
    assert sum(row["action"] == "product.session_started" for row in events) == 1
    created = [json.loads(row["metadata_json"]) for row in events if row["action"] == "product.project_created"]
    assert len(created) == 1
    assert created[0]["project_id"] == project_id
    assert "Private fixture project" not in json.dumps(created)


def test_reopen_restores_only_selected_project_inputs_without_session_secret(private_app):
    app, repository = private_app
    context = repository.local_context()
    first = repository.create_project(context, {"name": "First release"})
    second = repository.create_project(context, {"name": "Other release"})
    documents = [{"filename": "policy.md", "text": "Refunds are available within 30 days."}]
    repository.save_documents_and_chunks(context, documents, chunk_documents(documents), first)
    repository.create_dataset_version(
        context,
        first,
        "Reviewed cases",
        [
            {
                "case_id": "first-case",
                "question": "When can I claim a refund?",
                "expected_answer": "Within 30 days.",
                "expected_source": "policy.md",
                "category": "Policy",
                "should_escalate": False,
            }
        ],
    )
    repository.create_dataset_version(
        context,
        second,
        "Other cases",
        [
            {
                "case_id": "other-case",
                "question": "Other?",
                "expected_answer": "Other",
                "expected_source": "other.md",
                "category": "Other",
                "should_escalate": False,
            }
        ],
    )
    repository.create_target_version(
        context,
        first,
        "Staging assistant",
        "external_api",
        {
            "name": "Staging assistant",
            "endpoint": "https://first.example.test/answer",
            "request_template": {"question": "${question}"},
            "response_mappings": {"answer": "$.answer"},
            "headers": {"Authorization": "secret://SESSION_EXTERNAL_AUTH"},
            "retry_count": 0,
        },
    )
    _page(app, "Prepare")
    app.checkbox[0].check().run(timeout=30)
    _find(app.selectbox, "Reopen a saved project").set_value(f"First release · #{first}").run(timeout=30)
    _find(app.button, "Reopen project").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["project_id"] == first
    assert app.session_state["eval_df"]["case_id"].tolist() == ["first-case"]
    assert len(app.session_state["documents"]) == 1
    assert app.session_state["chunks"]
    assert app.session_state["external_target_config"]["endpoint"] == "https://first.example.test/answer"
    assert app.session_state["external_target_secret"] == ""
    assert any(row["action"] == "product.project_reopened" for row in _events(repository))


def test_public_sample_isolated_between_sessions_and_instrumented_once(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "public-demo")
    persistent_path = tmp_path / "must-not-open.sqlite3"
    monkeypatch.setattr(config, "DATABASE_PATH", persistent_path)
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{persistent_path}")
    database.set_repository(None)
    first = AppTest.from_file(config.ROOT_DIR / "app.py").run(timeout=30)
    assert not first.exception
    assert not any(button.label == "Start a project" for button in first.button)
    _find(first.button, "Try the sample review").click().run(timeout=30)
    assert not first.exception
    assert len(first.session_state["last_results"]) == 32
    first_repository = first.session_state["_demo_repository"]
    first_context = first.session_state["workspace_context"]
    first_session_id = first.session_state["analytics_session"]
    assert len(first_repository.list_runs(first_context)) == 1
    events = _events(first_repository)
    assert sum(row["action"] == "product.session_started" for row in events) == 1
    assert any(row["action"] == "product.sample_loaded" for row in events)
    assert any(row["action"] == "product.report_viewed" for row in events)
    second = AppTest.from_file(config.ROOT_DIR / "app.py").run(timeout=30)
    assert not second.exception
    assert second.session_state["analytics_session"] != first_session_id
    assert second.session_state["project_id"] is None
    assert second.session_state["last_results"].empty
    assert second.session_state["_demo_repository"].list_projects(second.session_state["workspace_context"]) == []
    _page(second, "Connect")
    assert not second.text_input
    assert not second.get("file_uploader")
    _page(first, "Review")
    assert len(first.session_state["last_results"]) == 32
    assert len(first_repository.list_runs(first_context)) == 1
    assert sum(row["action"] == "product.session_started" for row in _events(first_repository)) == 1
    assert not persistent_path.exists()
    database.set_repository(None)


def test_connection_save_validates_json_preserves_mapping_and_never_persists_credential(private_app, monkeypatch):
    app, repository = private_app
    monkeypatch.setattr(
        "src.targets._secure_urlopen", lambda *args, **kwargs: pytest.fail("Saving a connection must not call a target")
    )
    _find(app.button, "Start a project").click().run(timeout=30)
    app.checkbox[0].check().run(timeout=30)
    _find(app.text_input, "Project name").set_value("Connection fixture")
    _find(app.button, "Create project").click().run(timeout=30)
    _page(app, "Connect")
    credential = "opaque-partner-fixture-credential"
    _find(app.text_input, "Assistant endpoint").set_value("https://staging.example.test/answer")
    _find(app.text_input, "Session-only token or key").set_value(credential)
    from src.connection_settings import parse_connection_settings

    with pytest.raises(ValueError, match="could not be validated"):
        parse_connection_settings(b"{")
    assert app.session_state["external_target_config"] == {}
    app.session_state["imported_connection_draft"] = parse_connection_settings(
        json.dumps(
            {
                "name": "Support assistant",
                "endpoint": "https://staging.example.test/answer",
                "request_template": {"query": "${question}", "version": "fixture"},
                "headers": {"Authorization": "secret://SESSION_EXTERNAL_AUTH"},
            }
        ).encode()
    )
    app.run(timeout=30)
    _find(app.text_input, "Session-only token or key").set_value(credential)
    _find(app.text_input, "Answer field in the response").set_value("$.data.text")
    _find(app.text_input, "Citations field (optional)").set_value("")
    _find(app.number_input, "Retries after transient errors").set_value(0)
    _find(app.button, "Save connection").click().run(timeout=30)
    assert not app.exception
    assert not app.error
    config_saved = dict(app.session_state["external_target_config"])
    assert config_saved["request_template"] == {"query": "${question}", "version": "fixture"}
    assert config_saved["response_mappings"]["answer"] == "$.data.text"
    assert "citations" not in config_saved["response_mappings"]
    assert config_saved["retry_count"] == 0
    assert credential not in json.dumps(config_saved)
    assert _find(app.button, "Send one test request").disabled
    _page(app, "Start")
    _page(app, "Connect")
    assert not app.text_area
    assert app.session_state["external_target_config"]["request_template"] == config_saved["request_template"]
    assert not _find(app.checkbox, "Send the question using a single request field").value
    assert _find(app.text_input, "Citations field (optional)").value == ""
    _find(app.button, "Save connection").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["external_target_config"] == config_saved
    with repository.connection() as connection:
        stored = [
            row["configuration_json"] for row in connection.execute("SELECT configuration_json FROM target_versions")
        ]
        audits = [row["metadata_json"] for row in connection.execute("SELECT metadata_json FROM audit_logs")]
    assert stored
    assert credential not in json.dumps(stored + audits)

    requests = []

    class FixtureResponse:
        status = 200

        def read(self, size):
            return b'{"data":{"text":"Connection verified."}}'

        def close(self):
            pass

    def fixture_request(request, *, timeout):
        requests.append(json.loads(request.data))
        return FixtureResponse()

    monkeypatch.setattr("src.targets._secure_urlopen", fixture_request)
    _find(app.checkbox, "I authorize one connection check against this saved staging endpoint.").check().run(timeout=30)
    assert not app.exception
    _find(app.button, "Send one test request").click().run(timeout=30)
    assert not app.exception
    assert len(requests) == 1
    assert requests[0]["query"].startswith("Connectivity test:")
    assert requests[0]["version"] == "fixture"
    assert any("Connection check passed" in item.value for item in app.success)

    _page(app, "Prepare")
    _find(app.radio, "Preparation step").set_value("2 · Sources").run(timeout=30)
    _find(app.button, "Load sample documents").click().run(timeout=30)
    _find(app.radio, "Preparation step").set_value("3 · Cases").run(timeout=30)
    _find(app.button, "Load sample evaluation dataset").click().run(timeout=30)
    _page(app, "Evaluate")
    consent_label = "I authorize these external calls using approved test data and accept the provider cost."
    assert _find(app.button, "Run Evaluation").disabled
    _find(app.checkbox, consent_label).check().run(timeout=30)
    assert not app.exception
    assert not _find(app.button, "Run Evaluation").disabled
    _find(app.slider, "Retryable-error retries").set_value(3).run(timeout=30)
    assert not app.exception
    assert not _find(app.checkbox, consent_label).value
    assert _find(app.button, "Run Evaluation").disabled
    assert len(requests) == 1
