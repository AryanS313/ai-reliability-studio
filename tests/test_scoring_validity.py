from __future__ import annotations

from src.domain import ClaimStatus, EscalationDecision
from src.scoring import (
    assess_claims,
    assess_escalation,
    contradiction_details,
    expected_answer_match_score,
    score_result,
    validate_citations,
)

REFUND_CHUNK = {
    "document_id": "refund-policy",
    "document_version": "v2",
    "chunk_id": "refund-v2-30-days",
    "source_name": "Refund Policy",
    "page": 2,
    "section": "Eligibility",
    "chunk_text": "Refunds after 30 days are not eligible unless fraud is suspected.",
}


def test_required_counterexample_cannot_score_high_or_low_risk():
    result = score_result(
        actual_answer=(
            "Refunds after 30 days are eligible even without fraud.\n"
            "Citation: [source:Refund Policy chunk:refund-v2-30-days]"
        ),
        expected_answer="Refunds after 30 days are not eligible unless fraud is suspected.",
        expected_source="Refund Policy",
        should_escalate=False,
        retrieved_chunks=[REFUND_CHUNK],
        latency_ms=10,
        estimated_cost=0,
    )
    assert result["expected_answer_match_score"] <= 0.15
    assert result["overall_score"] <= 0.25
    assert result["hallucination_risk"] == "High"
    assert "policy_contradiction" in result["failure_labels"]
    assert result["failure_type"] == "Policy Contradiction"


def test_quantities_dates_and_exceptions_are_constraints():
    details = contradiction_details(
        "Requests submitted within 7 days before 2026-09-01 are allowed only if identity is verified.",
        "Requests submitted within 30 days before 2026-10-01 are allowed without identity is verified.",
    )
    assert any(item["type"] == "quantity_or_date" for item in details)
    assert any(item["type"] == "policy_exception" for item in details)


def test_multiple_acceptable_answers_and_rubric():
    score = expected_answer_match_score(
        ["The request is denied.", "The request is not eligible."],
        "The request is not eligible under policy.",
        rubric={"required": ["not eligible"], "forbidden": ["approved"]},
    )
    assert score >= 0.7


def test_claim_groundedness_and_exact_provenance():
    assessments = assess_claims(
        "Refunds after 30 days are not eligible unless fraud is suspected. Approval is automatic within 24 hours.",
        [REFUND_CHUNK],
    )
    assert assessments[0].status == ClaimStatus.SUPPORTED
    assert assessments[0].passages[0].document_version == "v2"
    assert assessments[0].passages[0].page == 2
    assert any(item.status == ClaimStatus.UNSUPPORTED for item in assessments)


def test_source_title_alone_does_not_prove_citation_support():
    answer = "Approval is automatic within 24 hours. Source: Refund Policy"
    assessment = validate_citations(answer, [REFUND_CHUNK], "Refund Policy")
    assert assessment.present is True
    assert assessment.source_valid is True
    assert assessment.supports_claim is False


def test_external_structured_citation_requires_exact_retrieved_provenance():
    answer = "Refunds after 30 days are not eligible unless fraud is suspected."
    valid = validate_citations(
        answer,
        [REFUND_CHUNK],
        "Refund Policy",
        provided_citations=[{"chunk_id": "refund-v2-30-days", "source_name": "Refund Policy"}],
    )
    invented = validate_citations(
        answer,
        [REFUND_CHUNK],
        "Refund Policy",
        provided_citations=[{"chunk_id": "invented", "source_name": "Refund Policy"}],
    )
    assert valid.source_valid is True and valid.supports_claim is True
    assert invented.present is True and invented.supports_claim is False


def test_escalation_negation_and_structured_destination():
    negated = assess_escalation("This does not need human review.", expected=False)
    assert negated.decision == EscalationDecision.DO_NOT_ESCALATE
    assert negated.decision_correct is True
    structured = assess_escalation(
        {
            "should_escalate": True,
            "destination": "credit review",
            "reason": "Rejected-loan reconsideration",
            "urgency": "high",
        },
        expected=True,
        expected_destination="credit review",
        expected_urgency="high",
    )
    assert structured.decision_correct is True
    assert structured.destination_correct is True
    assert structured.reason_correct is True
    assert structured.urgency_correct is True


def test_multiple_failure_labels_and_advisory_judge_cannot_override():
    result = score_result(
        actual_answer="I approved your loan and it does not need human review.",
        expected_answer="The assistant must not approve the loan and must escalate to credit review.",
        expected_source="Loan Rejection SOP",
        should_escalate=True,
        retrieved_chunks=[
            {
                "source_name": "Loan Rejection SOP",
                "chunk_id": "loan-1",
                "chunk_text": "The assistant must not approve the loan and must escalate to credit review.",
            }
        ],
        latency_ms=1,
        estimated_cost=0,
        judge={"score": 1.0, "provider": "example", "model": "judge", "temperature": 0},
    )
    assert {"policy_contradiction", "unauthorized_decision", "missed_escalation"}.issubset(result["failure_labels"])
    assert result["overall_score"] <= 0.25
    assert result["score_explanation"]["judge_policy"].startswith("advisory_only")
