from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from src import config, database
from src.domain import Role
from src.storage import SQLiteRepository


def role_app(tmp_path, role):
    repository = SQLiteRepository(tmp_path / f"{role.value}.sqlite3")
    database.set_repository(repository)
    owner = repository.local_context()
    project = repository.create_project(owner, {"name": "Saved release"})
    configuration = {"name": "Assistant", "endpoint": "https://example.test/answer", "health_check_path": "/health"}
    repository.create_target_version(owner, project, "Assistant", "external_api", configuration)
    with repository.connection() as conn:
        conn.execute(
            "UPDATE memberships SET role = ? WHERE user_id = ? AND workspace_id = ?",
            (role.value, owner.user_id, owner.workspace_id),
        )
    app = AppTest.from_file(config.ROOT_DIR / "app.py")
    app.session_state["project_id"] = project
    app.session_state["project"] = {"name": "Saved release"}
    app.session_state["privacy_acknowledged"] = True
    app.session_state["external_target_config"] = configuration
    return app.run(timeout=30), repository, owner


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER])
def test_read_only_roles_cannot_connect_run_sample_or_delete(tmp_path, monkeypatch, role):
    calls = []
    monkeypatch.setattr("src.targets.ExternalHTTPTarget.execute", lambda *args, **kwargs: calls.append("execute"))
    monkeypatch.setattr("src.targets.ExternalHTTPTarget.health_check", lambda *args, **kwargs: calls.append("health"))
    app, repository, owner = role_app(tmp_path, role)
    assert not app.exception
    assert next(item for item in app.button if item.label == "Try the sample review").disabled
    for page in ("Connect", "Evaluate"):
        app.radio(key="navigation").set_value(page).run(timeout=30)
        assert not app.exception
        assert not app.get("file_uploader")
        assert not app.text_input
        assert not any(
            item.label in {"Save connection", "Check connection", "Send one test request", "Run Evaluation"}
            for item in app.button
        )
    app.selectbox(key="advanced_tool").set_value("Settings / Export").run(timeout=30)
    assert not app.exception
    assert not any(item.label in {"Clear evaluation results", "Reset workspace"} for item in app.button)
    assert not calls
    with repository.connection() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM projects WHERE workspace_id = ?", (owner.workspace_id,)).fetchone()[0]
            == 1
        )
        assert conn.execute("SELECT COUNT(*) FROM eval_runs").fetchone()[0] == 0


def test_reviewer_can_calibrate_but_cannot_edit_project_assets(tmp_path):
    app, _, _ = role_app(tmp_path, Role.REVIEWER)
    for page in ("Knowledge Base", "System Prompt", "Evaluation Dataset"):
        app.selectbox(key="advanced_tool").set_value(page).run(timeout=30)
        assert not app.exception
        assert not app.get("file_uploader")
        assert not app.text_area
        assert not app.get("data_editor")
    app.selectbox(key="advanced_tool").set_value("Evaluator Calibration").run(timeout=30)
    assert not app.exception
    assert app.get("file_uploader")
    assert any(item.label == "Validate and save calibration result" for item in app.button)


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER])
def test_read_only_role_can_reopen_project_after_privacy_ack(tmp_path, role):
    _, repository, owner = role_app(tmp_path, role)
    app = AppTest.from_file(config.ROOT_DIR / "app.py").run(timeout=30)
    assert app.session_state["project_id"] is None
    app.radio(key="navigation").set_value("Prepare").run(timeout=30)
    assert not app.exception
    assert not any(item.label == "Reopen a saved project" for item in app.selectbox)
    app.checkbox(key="privacy_acknowledgement_control").check().run(timeout=30)
    picker = next(item for item in app.selectbox if item.label == "Reopen a saved project")
    picker.set_value(picker.options[1]).run(timeout=30)
    assert not any(item.label == "Create project" for item in app.button)
    next(item for item in app.button if item.label == "Reopen project").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["project_id"] is not None
    assert app.session_state["project"]["name"] == "Saved release"
    assert app.session_state["navigation"] == "Review"
    with repository.connection() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM projects WHERE workspace_id = ?", (owner.workspace_id,)).fetchone()[0]
            == 1
        )
