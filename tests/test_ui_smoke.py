from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src import database
from src.storage import SQLiteRepository


def test_streamlit_onboarding_and_target_setup_render_without_exceptions(tmp_path):
    database.set_repository(SQLiteRepository(tmp_path / "ui.sqlite3"))
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "AI Reliability Studio"
    assert "Target Setup" in app.radio[0].options
    assert "Evaluator Calibration" in app.radio[0].options
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert any("FinSure demo loaded" in message.value for message in app.success)
    app.radio[0].set_value("Target Setup").run(timeout=30)
    assert not app.exception
    rendered = " ".join(item.value for item in [*app.markdown, *app.warning, *app.info])
    assert "Synthetic" in rendered
    all_visible = " ".join(item.value for item in [*app.markdown, *app.warning, *app.info])
    assert "valid paths for a secrets.toml" not in all_visible.lower()
    assert str(tmp_path) not in all_visible


def test_streamlit_settings_renders_audited_export_controls(tmp_path):
    repository = SQLiteRepository(tmp_path / "exports-ui.sqlite3")
    database.set_repository(repository)
    context = repository.local_context()
    run_id = repository.create_run(
        context,
        run_name="report run",
        model_name="mock-model",
        mode="batch",
        unique_case_count=1,
        total_executions=1,
        target_type="synthetic_mock",
    )
    repository.save_result(
        context,
        run_id,
        {
            "case_id": "case-1",
            "question": "Question",
            "actual_answer": "Answer",
            "execution_status": "passed",
            "failure_type": "Passed",
            "prompt_version": "prompt-v1",
            "prompt_name": "Prompt",
            "target_version": "target-v1",
            "target_type": "synthetic_mock",
            "model_name": "mock-model",
            "overall_score": 0.8,
            "groundedness_score": 0.8,
            "citation_correctness_score": 0.8,
            "escalation_correctness_score": 1.0,
            "expected_answer_match_score": 0.8,
            "source_retrieval_score": 1.0,
            "hallucination_risk": "Low",
            "failure_labels": [],
        },
    )
    app = AppTest.from_file("app.py").run(timeout=30)
    app.radio[0].set_value("Settings / Export").run(timeout=30)
    assert not app.exception
    assert len(app.get("download_button")) == 3
    rendered = " ".join(item.value for item in [*app.markdown, *app.info])
    assert "separately selected synthetic target" in rendered.lower()
    metric_values = [str(item.value).lower() for item in app.metric]
    assert "local sqlite development storage" in metric_values
    assert str(tmp_path) not in rendered
    assert "database path" not in rendered.lower()


def test_streamlit_calibration_page_has_honest_empty_state(tmp_path):
    database.set_repository(SQLiteRepository(tmp_path / "calibration-ui.sqlite3"))
    app = AppTest.from_file("app.py").run(timeout=30)
    app.radio[0].set_value("Evaluator Calibration").run(timeout=30)
    assert not app.exception
    rendered = " ".join(item.value for item in [*app.markdown, *app.warning, *app.info, *app.caption])
    assert "held-out" in rendered.lower()
    assert "insufficient" in rendered.lower()
    assert "statistical confidence" in rendered.lower()
