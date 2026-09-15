from __future__ import annotations

import json

import pandas as pd
from bs4 import BeautifulSoup
from pandas.testing import assert_frame_equal

from src.reporting import html_report


def _observations() -> pd.DataFrame:
    common = {
        "prompt_name": "Improved Prompt",
        "prompt_version": "a" * 64,
        "candidate_id": "b" * 64,
        "target_version": "c" * 64,
        "dataset_version": "d" * 64,
        "threshold_version": "e" * 64,
        "target_type": "external_api",
        "target_name": "Support staging",
        "model_name": None,
        "category": "policy-exception",
        "severity": "high",
        "calibration_status": "insufficiently_calibrated",
        "evaluator_confidence": 0.8,
        "expected_answer": "A receipt is required for the refund.",
        "actual_answer": "No receipt is required.",
        "retrieved_chunks": [
            {"source_name": "Refund policy", "page": 2, "chunk_id": "f" * 64, "chunk_text": "A receipt is required."}
        ],
        "overall_score": 0.2,
        "groundedness_score": 0.2,
        "citation_correctness_score": 0.5,
        "escalation_correctness_score": 1.0,
        "estimated_cost": None,
        "latency_ms": 200.0,
    }
    return pd.DataFrame(
        [
            {
                **common,
                "case_id": "internal-case-1",
                "question": "Do I need a receipt?",
                "failure_type": "Policy Contradiction",
                "failure_labels": ["policy_contradiction"],
                "failure_reason_codes": ["negation_polarity_conflict"],
                "failure_evidence": {"unsupported_internals": {"payload": [1, 2]}},
                "execution_status": "passed",
            },
            {
                **common,
                "case_id": "internal-case-2",
                "question": "When will the refund arrive?",
                "failure_type": "Execution Error",
                "failure_labels": [],
                "failure_reason_codes": [],
                "execution_status": "timed_out",
                "actual_answer": "",
                "overall_score": None,
            },
        ]
    )


def _visible(report: str) -> tuple[BeautifulSoup, str]:
    soup = BeautifulSoup(report, "html.parser")
    for element in soup.find_all(["script", "style"]):
        element.decompose()
    return soup, soup.get_text(" ", strip=True)


def test_html_report_readable_checks_questions_sources_and_limits_preserve_data():
    observations = _observations()
    original = observations.copy(deep=True)
    report = html_report(observations)
    soup, visible = _visible(report)
    for phrase in [
        "Do I need a receipt?",
        "When will the refund arrive?",
        "Expected behavior",
        "A receipt is required for the refund.",
        "No receipt is required.",
        "Refund policy",
        "Page 2",
        "Next step",
        "Release checks",
        "Critical safety failures",
        "This call did not receive a quality score.",
        "human calibration",
    ]:
        assert phrase in visible
    for internal in [
        "gate_results",
        "failure_evidence",
        "negation_polarity_conflict",
        "unsupported_internals",
        "internal-case-1",
        "Improved Prompt",
        *[character * 64 for character in "abcdef"],
    ]:
        assert internal not in visible
    assert len(soup.select("article.case")) == 2
    assert "Not measured" in visible
    assert_frame_equal(observations, original)


def test_html_metadata_is_non_executable_and_injection_cannot_close_script():
    injection = '</script><script src="https://untrusted.test/steal"></script>'
    observations = _observations().assign(prompt_name=injection, target_name=injection, question=injection)
    report = html_report(observations)
    soup = BeautifulSoup(report, "html.parser")
    scripts = soup.find_all("script")
    assert len(scripts) == 1
    assert scripts[0].get("type") == "application/json"
    assert scripts[0].get("src") is None
    assert soup.find("img") is None
    metadata = json.loads(scripts[0].string)
    assert metadata["metadata"]["report_gate_manifest"]["configuration"]["minimum_overall_quality"] == 0.8
    assert len(metadata["candidates"]) == 1
    assert "\\u003c/script\\u003e" in report


def test_html_redacts_personal_information_and_credentials_from_visible_and_hidden_content():
    observations = _observations().assign(
        question="Email person@example.com with token sk-secret-value-123456",
        actual_answer="Authorization: Bearer shared-token-value",
        candidate_name="person@example.com",
    )
    report = html_report(observations)
    for value in ["person@example.com", "sk-secret-value-123456", "shared-token-value"]:
        assert value not in report
    assert "[REDACTED" in report


def test_synthetic_html_keeps_no_launch_verdict_and_hides_synthetic_engine_codes():
    observations = _observations().assign(target_type="synthetic_mock", model_name="mock-model")
    _, visible = _visible(html_report(observations))
    assert "Fictional sample: no launch verdict" in visible
    assert "Synthetic demonstration — no launch verdict" in visible
    assert "synthetic_mock" not in visible
    assert "mock-model" not in visible
    assert "Candidate instructions" in visible


def test_html_keeps_every_candidate_even_when_friendly_titles_match():
    observations = _observations().assign(
        execution_status="passed", prompt_name="Current Prompt", prompt_version=["a" * 64, "b" * 64]
    )
    soup, visible = _visible(html_report(observations))
    assert len(soup.select("section.candidate")) == 2
    assert "Evaluation 1:" in visible
    assert "Evaluation 2:" in visible
    assert "a" * 64 not in visible
    assert "b" * 64 not in visible


def test_empty_html_report_has_clear_empty_state_without_made_up_verdict():
    soup, visible = _visible(html_report(pd.DataFrame()))
    assert "No candidate evidence was recorded." in visible
    assert "No checks were recorded." in visible
    assert "The source of these answers was not recorded" in visible
    assert not soup.select("section.candidate")
