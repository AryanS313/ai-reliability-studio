from __future__ import annotations

import json

import pandas as pd
from streamlit.testing.v1 import AppTest

from src import config, database
from src.storage import SQLiteRepository


def case_app(tmp_path):
    repository = SQLiteRepository(tmp_path / "case-editor.sqlite3")
    database.set_repository(repository)
    context = repository.local_context()
    project = repository.create_project(context, {"name": "Question editing"})
    app = AppTest.from_file(config.ROOT_DIR / "app.py")
    app.session_state["project_id"] = project
    app.session_state["project"] = {"name": "Question editing"}
    app.session_state["privacy_acknowledged"] = True
    app.session_state["advanced_tool"] = "Evaluation Dataset"
    return app.run(timeout=30), repository, context


def test_new_question_draft_is_editable_before_coverage_validation(tmp_path):
    app, _, _ = case_app(tmp_path)
    next(item for item in app.button if item.label == "Create cases in the editor").click().run(timeout=30)
    assert not app.exception
    assert any(item.proto.editing_mode for item in app.dataframe)
    assert next(item for item in app.button if item.label == "Apply dataset edits").disabled
    assert not app.get("json")


def test_case_editor_hides_ids_and_nested_metadata_and_shows_friendly_coverage(tmp_path):
    app, _, _ = case_app(tmp_path)
    next(item for item in app.button if item.label == "Load sample evaluation dataset").click().run(timeout=30)
    assert not app.exception
    editor = next(item for item in app.dataframe if item.proto.editing_mode)
    frame = editor.value
    assert set(frame.columns) == {
        "case_id",
        "question",
        "expected_answer",
        "expected_source",
        "category",
        "handoff",
        "severity",
    }
    assert not any(isinstance(value, list | dict | tuple) for value in frame.to_numpy().ravel())
    configuration = json.loads(editor.proto.columns)
    assert configuration["case_id"]["hidden"] is True
    assert configuration["question"]["label"] == "Question"
    assert configuration["handoff"]["label"] == "Human handoff?"
    assert not app.get("json")
    captions = " ".join(item.value for item in app.caption)
    assert "saved alternatives" in captions
    assert "does not establish assistant quality" in captions


def test_editor_applies_visible_change_and_keeps_saved_nested_rules(tmp_path):
    app, repository, context = case_app(tmp_path)
    next(item for item in app.button if item.label == "Load sample evaluation dataset").click().run(timeout=30)
    before = app.session_state["eval_df"].copy(deep=True)
    editor = next(item for item in app.dataframe if item.proto.editing_mode)
    next(item for item in app.button if item.label == "Apply dataset edits").click()
    # AppTest exposes the table but has no data-editor interaction wrapper.
    # Submit the same widget-state protocol used by the browser with the save click.
    states = app._tree.get_widget_states()
    edit_state = states.widgets.add()
    edit_state.id = editor.proto.id
    edit_state.string_value = json.dumps(
        {
            "edited_rows": {0: {"question": "Revised question about the same policy"}},
            "added_rows": [],
            "deleted_rows": [],
        }
    )
    app._run(states, timeout=30)
    assert not app.exception
    after = app.session_state["eval_df"]
    assert after.iloc[0]["question"] == "Revised question about the same policy"
    for field in before.columns:
        if field == "question":
            continue
        expected = before.iloc[0][field]
        actual = after.iloc[0][field]
        if isinstance(expected, float) and pd.isna(expected):
            assert pd.isna(actual)
        else:
            assert actual == expected, field
    stored = repository.load_project_configuration(context, int(app.session_state["project_id"]))
    assert stored["dataset_records"][0]["question"] == "Revised question about the same policy"
    assert stored["dataset_records"][0]["case_id"] == before.iloc[0]["case_id"]
