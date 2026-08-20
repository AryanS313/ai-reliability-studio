from __future__ import annotations

import pandas as pd
import pytest

from src.datasets import (
    DatasetValidationException,
    coverage_analysis,
    dataset_quality_report,
    dataset_snapshot,
    normalize_dataset_frame,
    strict_bool,
    validate_dataset_frame,
)


def _valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "case-1",
                "question": "Can this proceed?",
                "category": "Policy",
                "expected_behavior": "answer",
                "severity": "critical",
                "tags": '["policy"]',
                "expected_answers": '["No"]',
                "should_escalate": "false",
            }
        ]
    )


def test_strict_boolean_rejects_unknown_values():
    with pytest.raises(ValueError, match="invalid boolean"):
        strict_bool("perhaps")


def test_row_level_blank_duplicate_and_boolean_errors():
    frame = pd.concat([_valid_frame(), _valid_frame()], ignore_index=True)
    frame.loc[1, "question"] = ""
    frame.loc[1, "should_escalate"] = "maybe"
    errors = validate_dataset_frame(frame, allow_legacy=False)
    codes = {(error.field, error.code) for error in errors}
    assert ("case_id", "duplicate") in codes
    assert ("question", "blank") in codes
    assert ("should_escalate", "invalid_boolean") in codes
    with pytest.raises(DatasetValidationException):
        normalize_dataset_frame(frame, allow_legacy=False)


def test_dataset_snapshot_hash_is_stable_and_coverage_warns():
    frame = _valid_frame()
    first = dataset_snapshot(frame, name="policy", version=1)
    second = dataset_snapshot(frame, name="policy", version=2)
    assert first["content_hash"] == second["content_hash"]
    analysis = coverage_analysis(frame)
    assert analysis["cases"] == 1
    assert analysis["warnings"]


def _launch_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": f"case-{index}",
                "question": f"Can policy case {index} proceed?",
                "category": "Policy",
                "expected_behavior": "answer",
                "severity": "critical" if index == 0 else "high",
                "tags": ["policy"],
                "expected_answers": ["Use the policy."],
                "expected_sources": ["Policy"],
                "should_escalate": False,
                "locale": "en-US",
                "environment": "staging",
                "split": "holdout",
                "purpose": f"Distinct boundary {index}",
                "severity_rationale": "A wrong answer can affect a policy decision.",
                "source_expectation": "Retrieve Policy.",
                "tuning_disclosure": "Candidate was not tuned on this holdout split.",
            }
            for index in range(30)
        ]
    )


def test_dataset_quality_can_qualify_a_complete_heldout_dataset():
    report = dataset_quality_report(
        _launch_frame(),
        available_sources={"Policy"},
        required_categories={"policy"},
    )
    assert report["launch_eligible"] is True
    assert report["errors"] == []
    assert report["version"]


def test_dataset_quality_blocks_missing_metadata_categories_sources_duplicates_and_tuning_disclosure():
    frame = _launch_frame()
    frame.loc[1, "question"] = frame.loc[0, "question"]
    frame.loc[2, "locale"] = ""
    frame.loc[3, "expected_sources"] = ["Missing Policy"]
    frame["tuning_disclosure"] = ""
    report = dataset_quality_report(
        frame,
        available_sources={"Policy"},
        required_categories={"policy", "privacy"},
        candidate_tuned_on_dataset=True,
    )
    assert report["launch_eligible"] is False
    joined = " ".join(report["errors"])
    assert "locale" in joined
    assert "Duplicate evaluation cases" in joined
    assert "privacy" in joined
    assert "Missing Policy" in joined
    assert "tuning disclosure" in joined
