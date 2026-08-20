from __future__ import annotations

from src.judges import JudgeConfiguration, LLMJudge
from src.scoring import score_result
from src.storage import SQLiteRepository
from src.targets import SecretResolver


def test_versioned_judge_parses_strict_output_and_remains_advisory():
    configuration = JudgeConfiguration(
        provider="example",
        model="judge-model-v1",
        api_key_reference="secret://JUDGE_KEY",
        temperature=0,
        seed=17,
    )

    def generator(**kwargs):
        return {
            "status": "passed",
            "answer": '{"score": 1, "label": "pass", "rationale": "Looks correct", "confidence": 0.9}',
        }

    judge = LLMJudge(configuration, SecretResolver({"JUDGE_KEY": "runtime-only"}), generator)
    assessment = judge.evaluate(
        question="Can the assistant approve a loan?",
        expected_answer="The assistant must not approve and must escalate.",
        actual_answer="I approved it; no review is needed.",
        retrieved_chunks=[{"chunk_id": "loan-1", "chunk_text": "The assistant must not approve and must escalate."}],
    )
    result = score_result(
        actual_answer="I approved it; no review is needed.",
        expected_answer="The assistant must not approve and must escalate.",
        expected_source="Loan SOP",
        should_escalate=True,
        retrieved_chunks=[
            {
                "source_name": "Loan SOP",
                "chunk_id": "loan-1",
                "chunk_text": "The assistant must not approve and must escalate.",
            }
        ],
        latency_ms=1,
        estimated_cost=0,
        judge=assessment,
    )
    assert assessment["configuration"]["configuration_version"] == configuration.version
    assert assessment["configuration"]["temperature"] == 0
    assert result["overall_score"] <= 0.25
    assert "unauthorized_decision" in result["failure_labels"]


def test_invalid_judge_output_is_unable_to_determine_without_throwing():
    judge = LLMJudge(
        JudgeConfiguration(provider="example", model="judge-model", api_key_reference="secret://KEY"),
        SecretResolver({"KEY": "runtime-only"}),
        lambda **kwargs: {"status": "passed", "answer": "not json"},
    )
    result = judge.evaluate(question="Q", expected_answer="E", actual_answer="A", retrieved_chunks=[])
    assert result["status"] == "unable_to_determine"
    assert result["error_code"] == "judge_invalid_response"


def test_judge_configuration_and_output_are_persisted_without_secret(tmp_path):
    repository = SQLiteRepository(tmp_path / "judge.sqlite3")
    context = repository.create_workspace("owner@example.com", "Judge")
    run_id = repository.create_run(
        context,
        run_name="judged run",
        model_name="target-model",
        mode="batch",
        unique_case_count=1,
        total_executions=1,
        target_type="foundation_model",
    )
    assessment = LLMJudge(
        JudgeConfiguration(provider="example", model="judge-model", api_key_reference="secret://KEY"),
        SecretResolver({"KEY": "runtime-secret-value"}),
        lambda **kwargs: {
            "status": "passed",
            "answer": '{"score": 0.8, "label": "pass", "rationale": "Supported", "confidence": 0.7}',
        },
    ).evaluate(question="Q", expected_answer="E", actual_answer="A", retrieved_chunks=[])
    repository.save_result(
        context,
        run_id,
        {
            "case_id": "case-1",
            "question": "Q",
            "actual_answer": "A",
            "execution_status": "passed",
            "failure_type": "Passed",
            "prompt_version": "prompt-v1",
            "target_version": "target-v1",
            "overall_score": 0.8,
            "failure_labels": [],
            "score_explanation": {"judge": assessment},
        },
    )
    with repository.connection() as conn:
        stored = conn.execute("SELECT * FROM judgments").fetchone()
    assert stored["model"] == "judge-model"
    assert stored["temperature"] == 0
    assert "runtime-secret-value" not in stored["output_json"]
