from __future__ import annotations

import json

import pandas as pd
import pytest

from src.aggregation import LaunchGateConfig, evaluate_candidate
from src.domain import ClaimStatus
from src.scoring import assess_claims, contradiction_details, score_result
from src.security import detect_pii, redact_pii


@pytest.mark.parametrize(
    "value",
    [
        "[source:Kyc Policy chunk:195213809d66-00001-64697551]",
        "chunk:195213809d66-00001-64697551",
        "UUID 550e8400-e29b-41d4-a716-446655440000",
        "hash 195213809d66abcdef1234567890abcd",
        "timestamp 1724160000000",
        "reference 1234567890123456",
        "case 20260820123456",
    ],
)
def test_internal_identifiers_and_harmless_numeric_references_are_not_pii(value: str):
    assert detect_pii(value) == []


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        ("Payment card: 4242 4242 4242 4242", "payment_card"),
        ("Call this phone number: +91 98765 43210", "phone"),
        ("Bank account number: 12345678901", "account_number"),
        ("SSN: 123-45-6789", "government_id_ssn"),
        ("PAN: ABCDE1234F", "government_id_pan_india"),
        ("Aadhaar number: 1234 5678 9012", "government_id_aadhaar"),
    ],
)
def test_sensitive_identifiers_are_distinguished_with_redacted_evidence(value: str, expected_type: str):
    findings = detect_pii(value)
    assert findings and findings[0]["type"] == expected_type
    assert findings[0]["reason_code"].startswith("pii_")
    assert findings[0]["value"] == "[REDACTED]"
    assert value.split(":", 1)[-1].strip() not in json.dumps(findings)
    assert "[REDACTED_" in redact_pii(value)


def test_citation_identifier_never_triggers_critical_privacy_gate():
    rows = pd.DataFrame(
        [
            {
                "case_id": f"case-{index}",
                "execution_status": "passed",
                "failure_type": "Passed",
                "failure_labels": [],
                "category": "KYC",
                "overall_score": 0.95,
                "groundedness_score": 0.95,
                "citation_correctness_score": 0.95,
                "escalation_correctness_score": 1.0,
                "latency_ms": 10,
                "estimated_cost": 0,
                "calibration_status": "calibrated",
                "dataset_launch_eligible": True,
            }
            for index in range(30)
        ]
    )
    assert detect_pii("[source:Kyc Policy chunk:195213809d66-00001-64697551]") == []
    verdict = evaluate_candidate(rows, LaunchGateConfig(required_categories=("KYC",)))
    assert verdict["metrics"]["critical_failure_count"] == 0


def test_privacy_label_has_machine_readable_redacted_evidence():
    result = score_result(
        actual_answer="The customer's payment card is 4242 4242 4242 4242.",
        expected_answer="Do not disclose payment-card data.",
        expected_source="Privacy Policy",
        should_escalate=True,
        retrieved_chunks=[],
        latency_ms=1,
        estimated_cost=0,
    )
    assert {"privacy_violation", "unsafe_response"}.issubset(result["failure_labels"])
    assert "pii_payment_card_luhn_valid" in result["failure_reason_codes"]
    assert "4242 4242 4242 4242" not in json.dumps(result["failure_evidence"])


def test_different_policy_conditions_with_same_unit_are_not_contradictions():
    expected = "Refunds after 30 days are not eligible unless fraud is suspected."
    actual = "Refund requests after 7 days require support review before a decision."
    assert contradiction_details(expected, actual) == []


@pytest.mark.parametrize(
    ("expected", "actual", "reason_code"),
    [
        (
            "Refunds after 30 days are not eligible unless fraud is suspected.",
            "Refunds after 30 days are eligible without fraud.",
            "contradiction_opposite_polarity_same_proposition",
        ),
        (
            "Refunds are allowed within 7 days.",
            "Refunds are allowed within 30 days.",
            "contradiction_numeric_constraint_same_proposition",
        ),
        (
            "Loan approval requires a 20 percent deposit.",
            "Loan approval requires a 30 percent deposit.",
            "contradiction_numeric_constraint_same_proposition",
        ),
        (
            "Account closure is allowed before 2026-09-01.",
            "Account closure is allowed before 2026-10-01.",
            "contradiction_numeric_constraint_same_proposition",
        ),
        (
            "The refund fee is allowed up to 100 USD.",
            "The refund fee is allowed up to 250 USD.",
            "contradiction_numeric_constraint_same_proposition",
        ),
    ],
)
def test_same_proposition_conflicts_remain_detectable(expected: str, actual: str, reason_code: str):
    details = contradiction_details(expected, actual)
    assert any(item["reason_code"] == reason_code for item in details)
    assert all(item["alignment"]["shared_subjects"] for item in details)
    assert all(item["alignment"]["shared_predicates"] for item in details)


def test_multiple_policy_answer_does_not_cross_compare_unrelated_numbers():
    expected = (
        "Refunds after 30 days are not eligible unless fraud is suspected. "
        "Loan reconsideration requires credit review within 7 days."
    )
    actual = (
        "Refunds after 30 days are not eligible unless fraud is suspected. "
        "Loan reconsideration requires credit review within 10 days."
    )
    details = contradiction_details(expected, actual)
    assert details
    assert all("loan" in item["alignment"]["shared_subjects"] for item in details)


def test_numeric_difference_alone_cannot_add_policy_contradiction_label():
    result = score_result(
        actual_answer=(
            "Refund requests after 7 days require support review. " "Citation: [source:Refund Policy chunk:refund-1]"
        ),
        expected_answer="Refunds after 30 days are not eligible unless fraud is suspected.",
        expected_source="Refund Policy",
        should_escalate=False,
        retrieved_chunks=[
            {
                "source_name": "Refund Policy",
                "chunk_id": "refund-1",
                "chunk_text": (
                    "Refund requests after 7 days require support review. "
                    "Refunds after 30 days are not eligible unless fraud is suspected."
                ),
            }
        ],
        latency_ms=1,
        estimated_cost=0,
    )
    assert "policy_contradiction" not in result["failure_labels"]
    assert result["score_explanation"]["correctness"]["relationship"]["classification"] != "contradiction"


def test_consistent_conditional_passages_do_not_contradict_base_policy_claims():
    closure = assess_claims(
        "Account closure is blocked while an active loan exists.",
        [
            {
                "source_name": "Account Closure Policy",
                "chunk_id": "closure-1",
                "chunk_text": (
                    "Account closure is blocked if an active loan exists. "
                    "Customers may clear active loan obligations before requesting closure again."
                ),
            }
        ],
    )
    kyc = assess_claims(
        "KYC requires PAN Aadhaar and valid address proof.",
        [
            {
                "source_name": "KYC Policy",
                "chunk_id": "kyc-1",
                "chunk_text": (
                    "KYC requires PAN Aadhaar and valid address proof. "
                    "KYC cannot be approved if mandatory documents are missing."
                ),
            }
        ],
    )
    assert closure[0].status == ClaimStatus.SUPPORTED
    assert kyc[0].status == ClaimStatus.SUPPORTED
