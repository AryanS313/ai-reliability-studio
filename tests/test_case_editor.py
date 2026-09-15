from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from src.case_editor import EDITOR_COLUMNS, case_editor_frame, coverage_findings, merge_case_edits
from src.datasets import coverage_analysis, normalize_dataset_frame, validate_dataset_frame


def rich_cases():
    frame = pd.DataFrame(
        [
            {
                "case_id": "case-original",
                "question": "Can I receive a refund after 30 days?",
                "expected_answer": "No, unless a documented exception applies.",
                "expected_answers": [
                    "No, unless a documented exception applies.",
                    "The normal limit is 30 days.",
                    "Review fraud exceptions.",
                ],
                "expected_source": "Refund policy",
                "expected_sources": ["Refund policy", "Exception policy"],
                "expected_behavior": "answer",
                "category": "policy-exception",
                "severity": "high",
                "should_escalate": False,
                "tags": ["policy-exception", "numeric-date", "customer-risk"],
                "rubric": {"must_preserve": ["30 days", "exceptions"], "weight": 2},
                "variables": {"customer_segment": "business"},
                "expected_passages": [{"chunk_id": "policy-30days"}],
                "expected_tool_calls": [{"name": "lookup_policy"}],
                "conversation_history": [{"role": "user", "content": "Explain the refund policy."}],
                "unacceptable_answers": ["All requests are automatically approved."],
                "language": "en",
                "locale": "en-GB",
                "environment": "staging",
                "split": "holdout",
                "purpose": "Check the time limit and exception together.",
                "severity_rationale": "Financial harm from an incorrect policy answer.",
                "source_expectation": "Use both policy sections.",
                "tuning_disclosure": "Not used for tuning.",
                "custom_partner_metadata": {"owner_team": "support", "revision": 3},
            },
            {
                "case_id": "case-second",
                "question": "Where is support?",
                "expected_answer": "Use the support portal.",
                "expected_answers": ["Use the support portal."],
                "expected_source": "Support guide",
                "expected_sources": ["Support guide"],
                "expected_behavior": "answer",
                "category": "support",
                "severity": "medium",
                "should_escalate": False,
                "tags": ["support"],
                "rubric": {},
                "variables": {},
                "locale": "en-GB",
                "environment": "staging",
                "split": "test",
            },
        ]
    )
    return normalize_dataset_frame(frame)


def test_editor_has_only_scalar_fields_and_preserves_unknown_handoff():
    source = rich_cases().drop(columns=["expected_answer", "expected_source"])
    source["should_escalate"] = source["should_escalate"].astype(object)
    source.at[0, "should_escalate"] = None
    projected = case_editor_frame(source)
    assert list(projected.columns) == EDITOR_COLUMNS
    assert projected.loc[0, "handoff"] == "Not specified"
    assert projected.loc[0, "severity"] == "High"
    assert not any(isinstance(value, list | dict | tuple) for value in projected.to_numpy().ravel())


def test_question_edit_preserves_ids_all_hidden_metadata_and_source_integrity_flags():
    source = rich_cases()
    original = deepcopy(source.to_dict("records")[0])
    projected = case_editor_frame(source)
    projected.loc[0, "question"] = "What exceptions apply after 30 days?"
    merged = merge_case_edits(source, projected)
    saved = merged.to_dict("records")[0]
    assert saved == {**original, "question": "What exceptions apply after 30 days?"}
    assert merged.attrs == source.attrs
    assert saved["rubric"] is not original["rubric"]
    assert source.to_dict("records")[0] == original
    assert saved["should_escalate"] is False


def test_main_reference_edits_update_aliases_without_deleting_alternatives():
    source = rich_cases()
    projected = case_editor_frame(source)
    projected.loc[0, "expected_answer"] = "After 30 days, review documented exceptions."
    projected.loc[0, "expected_source"] = "Updated refund policy"
    saved = merge_case_edits(source, projected).iloc[0]
    assert saved["expected_answer"] == "After 30 days, review documented exceptions."
    assert saved["expected_answers"] == [
        "After 30 days, review documented exceptions.",
        *source.iloc[0]["expected_answers"][1:],
    ]
    assert saved["expected_source"] == "Updated refund policy"
    assert saved["expected_sources"] == ["Updated refund policy", "Exception policy"]
    assert saved["expected_passages"] == source.iloc[0]["expected_passages"]
    assert saved["rubric"] == source.iloc[0]["rubric"]
    assert saved["expected_behavior"] == "answer"


def test_alias_not_in_alternatives_does_not_overwrite_an_imported_reference():
    source = rich_cases()
    source.at[0, "expected_answer"] = "Separate primary expectation"
    projected = case_editor_frame(source)
    projected.loc[0, "expected_answer"] = "Revised primary expectation"
    saved = merge_case_edits(source, projected).iloc[0]
    assert saved["expected_answers"] == ["Revised primary expectation", *source.iloc[0]["expected_answers"]]


def test_canonical_cases_without_legacy_columns_keep_their_schema_and_alternatives():
    source = rich_cases().drop(columns=["expected_answer", "expected_source"])
    projected = case_editor_frame(source)
    projected.loc[0, "expected_answer"] = "Revised canonical answer"
    merged = merge_case_edits(source, projected)
    assert "expected_answer" not in merged
    assert "expected_source" not in merged
    assert merged.iloc[0]["expected_answers"] == ["Revised canonical answer", *source.iloc[0]["expected_answers"][1:]]
    assert not validate_dataset_frame(merged, allow_legacy=False)


def test_row_addition_deletion_and_reordering_preserve_remaining_identity_and_rules():
    source = rich_cases()
    projected = case_editor_frame(source).iloc[[1]].copy()
    projected = pd.concat(
        [
            projected,
            pd.DataFrame(
                [
                    {
                        "case_id": None,
                        "question": "Who handles a dispute?",
                        "expected_answer": "The support team.",
                        "expected_source": "Support guide",
                        "category": "Human handoff",
                        "handoff": "Yes",
                        "severity": "Critical",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    merged = merge_case_edits(source, projected, new_id=lambda: "case-new")
    assert merged["case_id"].tolist() == ["case-second", "case-new"]
    assert merged.iloc[0]["expected_answers"] == source.iloc[1]["expected_answers"]
    assert merged.iloc[1]["expected_answers"] == ["The support team."]
    assert merged.iloc[1]["expected_sources"] == ["Support guide"]
    assert bool(merged.iloc[1]["should_escalate"])
    assert merged.iloc[1]["split"] == "development"
    assert merged.iloc[1]["severity"] == "critical"
    assert not validate_dataset_frame(merged)
    saved = normalize_dataset_frame(merged)
    assert saved["case_id"].tolist() == ["case-second", "case-new"]


@pytest.mark.parametrize("change", ["duplicate", "unknown", "empty", "incomplete", "bad-handoff"])
def test_invalid_edits_cannot_replace_identity_or_save_an_empty_or_malformed_set(change):
    source = rich_cases()
    projected = case_editor_frame(source)
    if change == "duplicate":
        projected.loc[1, "case_id"] = projected.loc[0, "case_id"]
    elif change == "unknown":
        projected.loc[0, "case_id"] = "other-project-case"
    elif change == "empty":
        projected = projected.iloc[0:0]
    elif change == "incomplete":
        projected.loc[0, "case_id"] = None
        projected.loc[0, "question"] = ""
    else:
        projected.loc[0, "handoff"] = "perhaps"
    with pytest.raises(ValueError):
        merge_case_edits(source, projected)


def test_required_field_and_enum_validation_is_not_weakened_by_editor():
    source = rich_cases()
    projected = case_editor_frame(source)
    projected.loc[0, "question"] = ""
    projected.loc[0, "severity"] = "Unimportant"
    errors = validate_dataset_frame(merge_case_edits(source, projected))
    assert {("question", "blank"), ("severity", "invalid_enum")} <= {(error.field, error.code) for error in errors}


def test_coverage_language_never_prints_raw_structures_or_version_identifiers():
    coverage = coverage_analysis(rich_cases())
    findings = coverage_findings(coverage)
    assert findings
    assert all("{" not in finding and "[" not in finding and "case-original" not in finding for finding in findings)
    assert coverage["quality_report"]["version"] not in " ".join(findings)
    assert any("risk areas" in finding for finding in findings)
