"""General regressions authored separately from the original 20-case diagnosis.

These examples prove specific deterministic behaviors, not production accuracy.
"""

from __future__ import annotations

import pytest

from src.domain import ClaimStatus
from src.scoring import assess_claims, contradiction_details, score_result, validate_citations


def chunk(text: str, chunk_id: str = "limits-1", **extra):
    return {
        "document_id": "operating-limits",
        "document_version": "revision-3",
        "source_name": "Operating Rules",
        "chunk_id": chunk_id,
        "chunk_text": text,
        **extra,
    }


def evaluate(expected: str, actual: str, *, chunks=None, citations=None, **extra):
    evidence = chunks if chunks is not None else [chunk(expected)]
    return score_result(
        expected_answer=expected,
        actual_answer=actual,
        expected_source="Operating Rules",
        should_escalate=extra.pop("should_escalate", False),
        retrieved_chunks=evidence,
        structured_escalation=extra.pop("structured_escalation", {"should_escalate": False}),
        latency_ms=1,
        estimated_cost=0,
        provided_citations=citations if citations is not None else [{"chunk_id": "limits-1"}],
        **extra,
    )


@pytest.mark.parametrize("unit", ["seats", "widgets", "megabytes", "API calls", "concurrent connections"])
def test_quantity_changes_are_detected_for_open_vocabulary_units(unit):
    expected = f"Enterprise accounts are allowed at most 320 {unit}."
    actual = f"Enterprise accounts are allowed at most 340 {unit}."
    result = evaluate(expected, actual)
    assert "policy_contradiction" in result["failure_labels"]
    assert result["overall_score"] <= 0.25
    assert result["claim_assessments"][0]["status"] == "contradicted"


@pytest.mark.parametrize(
    ("reference_relation", "answer_relation"),
    [("within", "after"), ("within", "before"), ("at most", "more than"), ("at least", "less than")],
)
def test_equal_numbers_do_not_hide_changed_relations(reference_relation, answer_relation):
    expected = f"Warranty requests are allowed {reference_relation} 18 days after delivery."
    actual = f"Warranty requests are allowed {answer_relation} 18 days after delivery."
    result = evaluate(expected, actual)
    assert "contradiction_numeric_relation_same_proposition" in result["failure_reason_codes"]
    assert result["failure_type"] == "Policy Contradiction"


def test_separate_request_appeal_and_processing_durations_remain_separate():
    policy = (
        "Warranty requests are allowed within 24 days after delivery. "
        "Warranty appeals are allowed within 6 days after denial. "
        "Warranty processing requires 4 days after approval."
    )
    correct = evaluate(policy, policy)
    assert correct["failure_type"] == "Passed"
    changed = policy.replace("6 days", "9 days")
    details = contradiction_details(policy, changed)
    assert details
    assert all("appeal" in item["alignment"]["shared_subjects"] for item in details)


@pytest.mark.parametrize(
    "answer",
    [
        "Workspace deletion is permitted whether or not outstanding backups are exported.",
        "Workspace deletion is permitted without outstanding backups being exported.",
    ],
)
def test_explicit_removal_of_approval_preconditions_is_not_supported(answer):
    result = evaluate("Workspace deletion is permitted only if outstanding backups are exported.", answer)
    assert result["failure_type"] != "Passed"
    assert result["groundedness_score"] == 0


def test_silent_precondition_omission_requires_review_without_inventing_a_conflict():
    expected = "Workspace deletion is permitted only if archived backups are exported."
    result = evaluate(expected, "Workspace deletion is permitted.")
    assert "policy_contradiction" not in result["failure_labels"]
    assert result["determination_state"] == "unable_to_determine"
    assert result["failure_type"] == "Needs Review"


def test_numeric_limits_cannot_replace_explicit_exemption():
    expected = "Warranty requests for defective units are eligible regardless of elapsed time and usage."
    answer = "Warranty requests for defective units are eligible only within 40 days when usage is at most 90 cycles."
    result = evaluate(expected, answer)
    assert "contradiction_exemption_restricted_same_proposition" in result["failure_reason_codes"]
    assert result["failure_type"] == "Policy Contradiction"


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("Accounts are allowed at most 250 seats.", "Accounts are permitted no more than two hundred fifty seats."),
        (
            "Uploads are allowed within 14 days after purchase.",
            "Uploads are permitted within a fortnight after buying.",
        ),
        ("Loans require a 15 percent deposit.", "Loans require a fifteen percent deposit."),
    ],
)
def test_explicitly_normalized_valid_paraphrases_can_still_pass(expected, actual):
    result = evaluate(expected, actual)
    assert result["failure_type"] == "Passed"
    assert result["groundedness_score"] == 1
    assert result["citation_correctness_score"] == 1


def test_unfamiliar_but_related_paraphrase_is_not_presented_as_proven_wrong():
    result = evaluate(
        "Accounts are eligible for closure only if outstanding invoices are paid.",
        "Settle every invoice before shutting down the account.",
    )
    assert result["failure_type"] == "Needs Review"
    assert "policy_contradiction" not in result["failure_labels"]
    assert "unsupported_claim" not in result["failure_labels"]
    assert result["determination_state"] == "unable_to_determine"


def test_swapping_actors_cannot_pass_using_same_bag_of_words():
    expected = "Support staff must notify account owners."
    answer = "Account owners must notify support staff."
    result = evaluate(expected, answer)
    assert result["failure_type"] == "Needs Review"
    assert result["groundedness_score"] == 0


def test_title_only_citation_is_presence_without_passage_support():
    expected = "Accounts are allowed at most 32 seats."
    result = evaluate(expected, expected + "\nSource: Operating Rules", citations=[])
    assert result["citation_present"] is True
    assert result["citation_source_valid"] is True
    assert result["citation_correctness_score"] == 0
    assert result["failure_type"] == "Citation Failure"


def test_same_title_cannot_transfer_support_to_wrong_passage():
    expected = "Accounts are allowed at most 32 seats."
    chunks = [chunk(expected, "seats"), chunk("Password recovery requires identity verification.", "recovery")]
    result = evaluate(expected, expected, chunks=chunks, citations=[{"chunk_id": "recovery"}])
    assert result["groundedness_score"] == 1
    assert result["citation_correctness_score"] == 0
    assert result["citation_details"][0]["supports_claims"] == []


@pytest.mark.parametrize(
    "bad_citation",
    [
        {"chunk_id": "limits-1", "source_name": "Invented Rules"},
        {"chunk_id": "limits-1", "document_version": "revision-2"},
        {"chunk_id": "limits-1", "document_id": "some-other-document"},
        {"chunk_id": "limits-1", "text_start": 92},
    ],
)
def test_valid_id_cannot_mask_inconsistent_provenance(bad_citation):
    expected = "Accounts are allowed at most 32 seats."
    result = evaluate(expected, expected, citations=[bad_citation])
    assert result["citation_correctness_score"] == 0
    assert result["citation_details"][0]["provenance_valid"] is False


def test_one_valid_citation_cannot_hide_another_invented_anchor():
    expected = "Accounts are allowed at most 32 seats."
    answer = expected + "\nCitation: [source:Operating Rules chunk:limits-1] [source:Operating Rules chunk:invented]"
    result = evaluate(expected, answer, citations=[])
    assert result["citation_correctness_score"] == 0
    assert len(result["citation_details"]) == 2


def test_citing_only_one_of_two_supported_claims_is_incomplete():
    first = "Accounts are allowed at most 32 seats."
    second = "Password recovery requires identity verification."
    result = evaluate(first + " " + second, first + " " + second, chunks=[chunk(first), chunk(second, "identity")])
    assert result["groundedness_score"] == 1
    assert result["citation_completeness"] == 0.5
    assert result["citation_correctness_score"] == 0


def test_location_that_matches_multiple_chunks_is_not_exact_provenance():
    policy = "Accounts are allowed at most 32 seats."
    assessment = validate_citations(
        policy,
        [chunk(policy, "first", page=1), chunk(policy, "second", page=1)],
        "Operating Rules",
        provided_citations=[
            {
                "document_id": "operating-limits",
                "document_version": "revision-3",
                "page": 1,
            }
        ],
    )
    assert assessment.supports_claim is False


@pytest.mark.parametrize(
    "action",
    [
        {"should_escalate": True, "destination": "sales", "urgency": "critical"},
        {"should_escalate": True, "destination": "operations", "urgency": "normal"},
        {"should_escalate": True, "destination": "operations"},
        {"should_escalate": True, "destination": "not operations", "urgency": "critical"},
    ],
)
def test_required_action_fields_affect_score_and_failure(action):
    expected = "Service outages require critical escalation to operations."
    result = evaluate(
        expected,
        expected,
        should_escalate=True,
        structured_escalation=action,
        expected_destination="operations",
        expected_urgency="critical",
    )
    assert result["failure_type"] == "Escalation Failure"
    assert result["escalation_correctness_score"] == 0
    assert "escalation_failure" in result["failure_labels"]
    assert result["hallucination_risk"] == "High"


def test_exact_action_fields_and_independent_claims_pass():
    expected = "Service outages require critical escalation to operations."
    result = evaluate(
        expected,
        expected,
        should_escalate=True,
        structured_escalation={"should_escalate": True, "destination": "operations", "urgency": "critical"},
        expected_destination="operations",
        expected_urgency="critical",
    )
    assert result["failure_type"] == "Passed"
    assert result["escalation_correctness_score"] == 1
    assert "Heuristic" in result["score_explanation"]["confidence_semantics"]


def test_related_source_is_not_sufficient_for_a_new_guarantee():
    assessments = assess_claims(
        "Workspace deletion is always guaranteed within 8 minutes.",
        [chunk("Workspace deletion requires staff approval before processing.")],
    )
    assert assessments[0].status != ClaimStatus.SUPPORTED


@pytest.mark.parametrize("modal", ["may", "can", "should"])
def test_optional_or_advisory_modality_is_not_equivalent_to_mandatory_action(modal):
    expected = "Support staff must notify account owners."
    result = evaluate(expected, f"Support staff {modal} notify account owners.")
    assert result["failure_type"] != "Passed"
    assert result["groundedness_score"] == 0


def test_distinct_number_word_alternatives_are_not_added_together():
    expected = "Requests are allowed within three days."
    answer = "Requests are allowed within one and two days."
    result = evaluate(expected, answer)
    assert result["failure_type"] != "Passed"
    assert result["groundedness_score"] == 0


def test_ambiguous_repeated_units_do_not_prove_cross_clause_contradiction():
    expected = "Transfer approval requires 2 days for review and 5 days for settlement."
    answer = "Transfer approval requires 5 days for settlement."
    assert contradiction_details(expected, answer) == []


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        (
            "Exports require administrator approval and a recorded audit entry.",
            "Exports require administrator approval.",
        ),
        (
            "Support staff must notify account owners and record the incident.",
            "Support staff must notify account owners.",
        ),
        (
            "Requests require proof of purchase. Appeals require a denial reference.",
            "Requests require proof of purchase.",
        ),
    ],
)
def test_grounded_partial_answer_cannot_satisfy_complete_expected_behavior(expected, actual):
    result = evaluate(expected, actual)
    assert result["failure_type"] != "Passed"
    assert result["expected_answer_match_score"] < 0.7


def test_explicit_required_rubric_item_cannot_be_averaged_away():
    expected = "Appeals require a denial reference."
    result = evaluate(expected, expected, rubric={"required": ["case identifier"]})
    assert result["expected_answer_match_score"] < 0.7
    assert result["failure_type"] != "Passed"
