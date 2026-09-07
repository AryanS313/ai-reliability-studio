"""Known-issue regressions with distinct, contrastive fictional policy examples.

These do not constitute an independent benchmark or establish production accuracy.
"""

from __future__ import annotations

import pytest

from src.domain import ClaimStatus
from src.scoring import assess_claims, contradiction_details, score_result

BASE = "Data imports are allowed within 9 hours after approval if the payload is at most 48 GB."
EXEMPTION = (
    "Premium accounts with a valid compliance certificate are exempt from the size limit, "
    "but the 9-hour time limit still applies."
)


def evaluate(answer, *, reference=EXEMPTION, evidence=BASE + " " + EXEMPTION):
    chunks = (
        [{"source_name": "Import Rules", "chunk_id": "import-3", "chunk_text": evidence}]
        if evidence is not None
        else []
    )
    return score_result(
        actual_answer=answer,
        expected_answer=reference,
        expected_source="Import Rules" if chunks else "Out of Scope",
        should_escalate=False,
        retrieved_chunks=chunks,
        latency_ms=1,
        estimated_cost=0,
        structured_escalation={"should_escalate": False},
        provided_citations=[{"chunk_id": "import-3"}] if chunks else [],
    )


def test_preserved_deadline_does_not_restrict_an_independent_size_exemption():
    answer = (
        "Premium accounts using a valid compliance certificate can import a payload larger than 48 GB, "
        "provided the import is still within 9 hours after approval."
    )
    result = evaluate(answer)
    assert "policy_contradiction" not in result["failure_labels"]
    assert "unsupported_claim" not in result["failure_labels"]
    # The limited grammar still does not prove this unfamiliar paraphrase.
    assert result["failure_type"] == "Needs Review"
    assert result["determination_state"] == "unable_to_determine"


@pytest.mark.parametrize(
    "subject",
    [
        "Premium accounts",
        "Accounts with a valid compliance certificate",
        "Premium accounts with an expired certificate",
    ],
)
def test_omitting_or_changing_exemption_prerequisites_cannot_pass(subject):
    result = evaluate(f"{subject} can import a payload larger than 48 GB within 9 hours after approval.")
    assert result["failure_type"] != "Passed"
    assert result["groundedness_score"] == 0


def test_reimposing_waived_size_bound_is_still_a_hard_conflict():
    result = evaluate(
        "Premium accounts with a valid compliance certificate can import only payloads at most 48 GB "
        "within 9 hours after approval."
    )
    assert result["failure_type"] == "Policy Contradiction"
    assert "contradiction_exemption_restricted_same_proposition" in result["failure_reason_codes"]


@pytest.mark.parametrize("condition", ["an expired compliance certificate", "no valid compliance certificate"])
def test_restricted_non_exempt_subject_is_not_falsely_in_conflict(condition):
    answer = f"Premium accounts with {condition} can import only payloads at most 48 GB within 9 hours."
    assert not contradiction_details(EXEMPTION, answer)


def test_exemption_prerequisite_after_the_grant_must_also_be_preserved():
    expected = "Accounts are exempt from the size limit only if a compliance certificate is valid."
    ordinary = "Accounts are allowed payloads at most 48 GB."
    assert not contradiction_details(expected, ordinary)
    assert contradiction_details(expected, ordinary[:-1] + " only if a compliance certificate is valid.")


def test_exempting_wrong_property_does_not_hide_a_reimposed_size_bound():
    result = evaluate(
        "Premium accounts with a valid compliance certificate are exempt from the time limit, "
        "but payloads must be at most 48 GB."
    )
    assert result["failure_type"] == "Policy Contradiction"


def test_ordinary_deadline_violation_is_not_excused_by_a_size_exemption_elsewhere():
    answer = "Data imports are allowed within 12 hours after approval if the payload is at most 48 GB."
    result = evaluate(answer, reference=BASE)
    assert result["failure_type"] == "Policy Contradiction"
    assert "contradiction_numeric_constraint_same_proposition" in result["failure_reason_codes"]


@pytest.mark.parametrize(
    ("scope", "permitted_bound", "forbidden_bound"),
    [
        ("time", "at most 7 seats", "within 7 days"),
        ("seat", "within 7 days", "at most 7 seats"),
        ("size", "within 7 days", "at most 7 megabytes"),
        ("price", "within 7 days", "at most 7 dollars"),
    ],
)
def test_exemption_restrictions_are_bound_to_their_unit_dimension(scope, permitted_bound, forbidden_bound):
    expected = f"Certified accounts are eligible regardless of the {scope} limit."
    assert not contradiction_details(expected, f"Certified accounts are eligible {permitted_bound}.")
    assert contradiction_details(expected, f"Certified accounts are eligible {forbidden_bound}.")


def test_exact_preserved_policy_is_still_supported():
    result = evaluate(EXEMPTION, evidence=EXEMPTION)
    assert result["failure_type"] == "Passed"
    assert result["groundedness_score"] == 1


@pytest.mark.parametrize(
    "answer",
    [
        "I cannot determine whether overseas claims are eligible from the available material.",
        "We are unable to confirm the required renewal fee from this evidence.",
        "The provided evidence does not establish a guaranteed replacement service.",
        "I do not have enough information to know whether refunds are allowed.",
    ],
)
def test_epistemic_abstention_with_no_evidence_is_unknown_not_wrong_or_correct(answer):
    result = evaluate(answer, reference="The evidence does not establish the requested policy.", evidence=None)
    assert result["failure_type"] == "Needs Review"
    assert result["determination_state"] == "unable_to_determine"
    assert "unsupported_claim" not in result["failure_labels"]
    assert "policy_contradiction" not in result["failure_labels"]
    assert result["groundedness_score"] == 0


@pytest.mark.parametrize("separator", [". ", "; ", ", but ", " but ", ", and ", ", "])
def test_abstention_cannot_hide_a_following_unsupported_guarantee(separator):
    answer = "I cannot determine the replacement terms" + separator + "A free replacement is guaranteed."
    result = evaluate(answer, reference="The evidence does not establish replacement terms.", evidence=None)
    assert result["failure_type"] == "Unsupported Claim"
    assert "unsupported_claim" in result["failure_labels"]
    assert result["groundedness_score"] == 0


def test_abstention_cannot_hide_explicit_first_person_commitment_in_a_conjunction():
    result = evaluate(
        "I cannot determine the refund terms and we will refund the entire purchase.",
        reference="The evidence does not establish refund terms.",
        evidence=None,
    )
    assert result["failure_type"] == "Unsupported Claim"
    assert "unsupported_claim" in result["failure_labels"]


def test_inability_to_perform_action_is_a_policy_claim_not_epistemic_abstention():
    claims = assess_claims("Customers cannot cancel an approved transfer.", [])
    assert claims[0].status == ClaimStatus.UNSUPPORTED
    assert contradiction_details(
        "Customers are allowed to cancel an approved transfer.",
        "Customers are not allowed to cancel an approved transfer.",
    )


def test_abstention_is_not_supported_just_because_source_repeats_it():
    answer = "I cannot confirm whether refunds are allowed."
    result = evaluate(answer, reference=answer, evidence=answer)
    assert result["failure_type"] == "Needs Review"
    assert result["groundedness_score"] == 0
