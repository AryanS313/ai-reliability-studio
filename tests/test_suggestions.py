import pandas as pd

from src.suggestions import (
    FAILURE_SUGGESTIONS,
    comparison_language,
    generate_improved_prompt,
    run_level_insight_summary,
    suggestion_for_failure,
)


def test_each_failure_type_returns_non_empty_suggestion():
    for failure_type in FAILURE_SUGGESTIONS:
        assert suggestion_for_failure(failure_type)


def test_passed_returns_no_action_required():
    assert suggestion_for_failure("Passed") == "No action required."


def test_generic_prompt_proposal_preserves_input_without_inventing_financial_policy():
    current = "Answer subscription questions. Route billing disputes to the account team."
    proposal = generate_improved_prompt(current)
    assert current in proposal
    assert "customer support" in proposal
    assert "Follow the escalation conditions and destinations in the supplied policies" in proposal
    assert "loan approval" not in proposal
    assert "fintech" not in proposal
    assert "until evaluated and promoted" in proposal


def test_unversioned_runs_cannot_claim_prompt_superiority():
    rows = pd.DataFrame(
        [
            {
                "case_id": "same",
                "question": "same",
                "prompt_name": name,
                "target_type": "external_api",
                "overall_score": score,
                "execution_status": "passed",
            }
            for name, score in [("old", 0.2), ("new", 0.9)]
        ]
    )
    assert comparison_language(rows)["status"] == "inconclusive"
    assert "outperformed" not in comparison_language(rows)["summary"]


def test_all_failed_run_has_recovery_message_without_quality_columns():
    rows = pd.DataFrame(
        [
            {"case_id": "same", "prompt_name": name, "target_type": "external_api", "execution_status": "failed"}
            for name in ["old", "new"]
        ]
    )
    assert comparison_language(rows)["status"] == "missing_data"
    assert "No answer quality evidence" in run_level_insight_summary(rows)
