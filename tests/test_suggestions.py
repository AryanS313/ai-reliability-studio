from src.suggestions import FAILURE_SUGGESTIONS, suggestion_for_failure


def test_each_failure_type_returns_non_empty_suggestion():
    for failure_type in FAILURE_SUGGESTIONS:
        assert suggestion_for_failure(failure_type)


def test_passed_returns_no_action_required():
    assert suggestion_for_failure("Passed") == "No action required."

