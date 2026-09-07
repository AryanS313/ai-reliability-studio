"""Contrast citation uncertainty with established defects, using independent inputs."""

from __future__ import annotations

import pytest

from src.scoring import score_result

POLICY = "Accounts are eligible for closure only if outstanding invoices are paid."
PARAPHRASE = "Settle every invoice before shutting down the account."


def passage(text: str, chunk_id: str = "closure"):
    return {
        "document_id": "operations",
        "document_version": "edition-4",
        "source_name": "Operations Manual",
        "chunk_id": chunk_id,
        "chunk_text": text,
    }


def evaluate(answer=PARAPHRASE, *, policy=POLICY, chunks=None, citations=None):
    return score_result(
        actual_answer=answer,
        expected_answer=policy,
        expected_source="Operations Manual",
        should_escalate=False,
        retrieved_chunks=[passage(policy)] if chunks is None else chunks,
        provided_citations=[{"chunk_id": "closure"}] if citations is None else citations,
        structured_escalation={"should_escalate": False},
        latency_ms=1,
        estimated_cost=0,
    )


def test_resolved_unfamiliar_paraphrase_is_unverified_without_false_citation_failure():
    result = evaluate()
    assert result["citation_present"] and result["citation_source_valid"]
    assert result["citation_details"][0]["provenance_valid"]
    assert result["citation_support_state"] == "unverified"
    assert result["citation_details"][0]["support_state"] == "unverified"
    assert result["score_explanation"]["citations"]["support_state"] == "unverified"
    assert result["citation_correctness_score"] == 0
    assert result["citation_supports_claim"] is False
    assert result["citation_completeness"] == 0
    assert result["failure_labels"] == ["evaluator_uncertain"]
    assert "citation_support_unverified" in result["failure_reason_codes"]
    assert "citation_does_not_support_claim" not in result["failure_reason_codes"]
    assert result["failure_type"] == "Needs Review"
    assert result["determination_state"] == "unable_to_determine"


@pytest.mark.parametrize(
    ("citations", "state", "reason"),
    [
        ([], "missing", "citation_missing"),
        ([{"chunk_id": "missing"}], "unresolved", "citation_source_unresolved"),
        ([{"source_name": "Operations Manual"}], "unresolved", "citation_provenance_unresolved"),
        ([{"chunk_id": "closure", "document_version": "edition-3"}], "unresolved", "citation_source_unresolved"),
        ([{"chunk_id": "closure", "source_name": "Unrelated Manual"}], "unresolved", "citation_source_unresolved"),
        ([{"chunk_id": "closure"}, {"chunk_id": "invented"}], "unresolved", "citation_source_unresolved"),
    ],
)
def test_uncertain_claim_cannot_hide_missing_or_invalid_citation(citations, state, reason):
    result = evaluate(citations=citations)
    assert result["citation_support_state"] == state
    assert result["citation_correctness_score"] == 0
    assert "citation_failure" in result["failure_labels"]
    assert "evaluator_uncertain" in result["failure_labels"]
    assert reason in result["failure_reason_codes"]
    assert result["failure_type"] != "Passed"


def test_supported_exact_citation_still_earns_credit_and_passes():
    result = evaluate(POLICY)
    assert result["citation_support_state"] == "supported"
    assert result["citation_correctness_score"] == 1
    assert result["citation_completeness"] == 1
    assert result["failure_labels"] == []
    assert result["failure_type"] == "Passed"


def test_claim_supported_elsewhere_does_not_turn_cited_paraphrase_uncertainty_into_defect():
    result = evaluate(
        POLICY,
        chunks=[passage(POLICY, "exact"), passage(PARAPHRASE)],
    )
    assert result["claim_assessments"][0]["status"] == "supported"
    assert result["groundedness_score"] == 1
    assert result["citation_support_state"] == "unverified"
    assert result["citation_correctness_score"] == 0
    assert result["failure_labels"] == ["evaluator_uncertain"]
    assert result["failure_type"] == "Needs Review"
    assert result["determination_state"] == "unable_to_determine"


def test_wrong_passage_from_same_source_remains_established_defect():
    policy = "Project uploads are allowed at most 42 files."
    result = evaluate(
        policy,
        policy=policy,
        chunks=[passage(policy, "uploads"), passage("Password changes require identity verification.")],
    )
    assert result["groundedness_score"] == 1
    assert result["citation_support_state"] == "unsupported"
    assert "citation_failure" in result["failure_labels"]
    assert result["failure_type"] == "Citation Failure"


def test_contradicted_cited_constraint_remains_failure():
    policy = "Project uploads are allowed at most 42 files."
    result = evaluate("Project uploads are allowed at most 52 files.", policy=policy)
    assert result["citation_support_state"] == "unsupported"
    assert result["citation_details"][0]["support_state"] == "contradicted"
    assert "citation_failure" in result["failure_labels"]
    assert "policy_contradiction" in result["failure_labels"]
    assert result["overall_score"] <= 0.25


def test_other_citations_and_uncertain_claim_cannot_mask_contradicted_anchor():
    restrictive = "Report uploads are allowed at most 9 files."
    permissive = "Report uploads are allowed at most 12 files."
    result = evaluate(
        permissive + " " + PARAPHRASE,
        policy=restrictive + " " + POLICY,
        chunks=[passage(restrictive, "restrictive"), passage(permissive, "permissive"), passage(POLICY)],
        citations=[{"chunk_id": "restrictive"}, {"chunk_id": "permissive"}, {"chunk_id": "closure"}],
    )
    contradicted = result["citation_details"][0]
    assert contradicted["contradicted_claims"]
    assert contradicted["unverified_claims"]
    assert contradicted["support_state"] == "contradicted"
    assert result["citation_support_state"] == "unsupported"
    assert result["citation_correctness_score"] == 0
    assert "citation_failure" in result["failure_labels"]
    assert "policy_contradiction" in result["failure_labels"]


def test_uncertain_claim_does_not_hide_uncited_supported_claim():
    established = "Password changes require identity verification."
    result = evaluate(
        PARAPHRASE + " " + established,
        policy=POLICY + " " + established,
        chunks=[passage(POLICY), passage(established, "passwords")],
    )
    assert {claim["status"] for claim in result["claim_assessments"]} == {"supported", "unverifiable"}
    assert result["citation_details"][0]["support_state"] == "unverified"
    assert result["citation_support_state"] == "unsupported"
    assert "citation_failure" in result["failure_labels"]
    assert "evaluator_uncertain" in result["failure_labels"]


def test_partial_known_and_unverified_coverage_is_review_without_credit():
    established = "Password changes require identity verification."
    result = evaluate(
        PARAPHRASE + " " + established,
        policy=POLICY + " " + established,
        chunks=[passage(POLICY), passage(established, "passwords")],
        citations=[{"chunk_id": "closure"}, {"chunk_id": "passwords"}],
    )
    assert result["citation_support_state"] == "unverified"
    assert result["citation_completeness"] == 0.5
    assert result["citation_correctness_score"] == 0
    assert result["failure_labels"] == ["evaluator_uncertain"]
    assert result["failure_type"] == "Needs Review"


def test_uncertainty_cannot_hide_unsupported_guarantee():
    result = evaluate(PARAPHRASE + " Every workspace is guaranteed a private concierge.")
    assert "unsupported_claim" in result["failure_labels"]
    assert "citation_failure" in result["failure_labels"]
    assert result["citation_support_state"] == "unsupported"
    assert result["failure_type"] == "Unsupported Claim"


def test_no_extracted_claims_with_resolved_citation_requires_review():
    result = evaluate("", citations=[{"chunk_id": "closure"}])
    assert result["citation_support_state"] == "unverified"
    assert result["citation_correctness_score"] == 0
    assert result["failure_type"] == "Needs Review"
    assert result["determination_state"] == "unable_to_determine"
