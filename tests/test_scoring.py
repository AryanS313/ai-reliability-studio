from src.scoring import (
    citation_correctness_score,
    detect_escalation,
    escalation_correctness_score,
    expected_answer_match_score,
    hallucination_risk,
    overall_reliability_score,
    source_retrieval_score,
)


def test_expected_answer_match_score_uses_keyword_overlap():
    score = expected_answer_match_score(
        "PAN Aadhaar and address proof are required.",
        "KYC requires PAN, Aadhaar, and valid address proof.",
    )
    assert score >= 0.75


def test_source_retrieval_score_matches_expected_source():
    assert source_retrieval_score("Refund Policy", ["Refund Policy", "KYC Policy"]) == 1
    assert source_retrieval_score("Loan Rejection SOP", ["Refund Policy"]) == 0


def test_out_of_scope_source_scores_when_answer_refuses():
    answer = "I do not have enough information in the uploaded documents to answer this confidently."
    # Retrieval and response behavior are independent. A refusal does not turn
    # an out-of-scope case into a successful source retrieval or citation.
    assert source_retrieval_score("Out of Scope", [], answer) == 0
    assert citation_correctness_score(answer, "Out of Scope") == 0


def test_citation_and_escalation_correctness():
    answer = "Answer: Manual loan approval cannot be provided. Sources: Loan Rejection SOP. Escalation Required: Yes"
    assert citation_correctness_score(answer, "Loan Rejection SOP") == 0
    chunks = [
        {
            "source_name": "Loan Rejection SOP",
            "chunk_id": "loan-1",
            "chunk_text": "Manual loan approval cannot be provided and requests require credit review.",
        }
    ]
    # A display title establishes presence, not exact evidence provenance.
    assert citation_correctness_score(answer, "Loan Rejection SOP", chunks) == 0
    cited = (
        "Manual loan approval cannot be provided and requests require credit review.\n"
        "Citation: [source:Loan Rejection SOP chunk:loan-1]"
    )
    assert citation_correctness_score(cited, "Loan Rejection SOP", chunks) == 1
    assert detect_escalation(answer) is True
    assert escalation_correctness_score(answer, True) == 1


def test_hallucination_risk_flags_missing_source():
    risk = hallucination_risk(
        actual_answer="Refunds are approved after 90 days.",
        expected_answer="Refunds after 30 days are generally not eligible unless fraud is suspected.",
        expected_source="Refund Policy",
        retrieved_sources=[],
        retrieved_chunks=[],
        should_escalate=False,
    )
    assert risk == "High"


def test_overall_reliability_score_formula():
    assert overall_reliability_score(1, 1, 1, 0.5, 1) == 0.9
