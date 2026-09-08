from __future__ import annotations

import json
from copy import deepcopy

import pandas as pd
import pytest

from src.saved_responses import compare_response_reviews
from src.ui_workflows import (
    evaluate_review_workspace,
    new_review_workspace,
    read_review_workspace,
    replacement_batch,
    sample_replacements,
    sample_review_workspace,
    save_case_review,
)


def restored(workspace, batch="baseline"):
    return evaluate_review_workspace(read_review_workspace(json.dumps(workspace).encode()), batch)


def fully_reviewed_workspace():
    workspace = sample_review_workspace()
    baseline = evaluate_review_workspace(workspace)
    for index, row in enumerate(baseline.to_dict(orient="records")):
        review = {key: row[key] for key in ("case_id", "response_hash", "case_version", "knowledge_base_version")}
        review.update(
            decision="supported" if index == 0 else "failed",
            reviewer="Fictional reviewer \u00e9",
            reviewer_kind="human" if index == 0 else "ai_assisted",
            note="Fixture source check \u2014 preserved exactly.",
            reviewed_at="2026-09-08T06:00:00+00:00",
        )
        workspace, baseline = save_case_review(workspace, "baseline", baseline, review)
    workspace["candidate"] = replacement_batch(
        sample_replacements(workspace), "fictional-v2", "2026-09-08T06:00:01+00:00"
    )
    candidate = evaluate_review_workspace(workspace, "candidate")
    for row in candidate.to_dict(orient="records"):
        review = {key: row[key] for key in ("case_id", "response_hash", "case_version", "knowledge_base_version")}
        review.update(
            decision="supported",
            reviewer="Replacement fixture reviewer",
            reviewer_kind="ai_assisted",
            note="Replacement source check.",
            reviewed_at="2026-09-08T06:00:02+00:00",
        )
        workspace, candidate = save_case_review(workspace, "candidate", candidate, review)
    return workspace, baseline, candidate


def test_baseline_and_partial_replacements_preserve_decisions_attribution_and_comparison():
    workspace, baseline, candidate = fully_reviewed_workspace()
    copy = read_review_workspace(json.dumps(workspace, ensure_ascii=False).encode())
    assert copy == workspace
    for batch, before in (("baseline", baseline), ("candidate", candidate)):
        after = evaluate_review_workspace(copy, batch)
        stable = [
            "case_id",
            "reviewer",
            "reviewer_kind",
            "review_note",
            "reviewed_at",
            "review_hash",
            "case_version",
            "response_hash",
            "knowledge_base_version",
            "review_decision",
            "human_review_status",
            "actual_answer",
            "structured_escalation",
        ]
        pd.testing.assert_frame_equal(before[stable], after[stable])
    assert compare_response_reviews(restored(copy), restored(copy, "candidate"))["counts"] == {"resolved": 2}


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "question",
        "answer",
        "citation",
        "escalation",
        "review_hash",
        "duplicate_review",
        "unknown_review",
        "missing_answer",
        "duplicate_answer",
        "unknown_replacement",
        "wrong_schema",
        "invalid_review_kind",
        "missing_reviewer",
        "missing_note",
    ],
)
def test_corrupt_or_incompatible_inputs_fail_explicitly(change):
    workspace, _, _ = fully_reviewed_workspace()
    if change == "source":
        workspace["sources"][0]["chunk_text"] += " Changed."
    elif change == "question":
        workspace["dataset"][0]["question"] += " Changed?"
    elif change == "answer":
        workspace["baseline"]["responses"][0]["actual_answer"] += " Changed."
    elif change == "citation":
        workspace["baseline"]["responses"][0]["citations"] = []
    elif change == "escalation":
        workspace["baseline"]["responses"][0]["escalation"] = {"should_escalate": True}
    elif change == "review_hash":
        workspace["baseline"]["reviews"][0]["response_hash"] = "stale"
    elif change == "duplicate_review":
        workspace["baseline"]["reviews"].append(deepcopy(workspace["baseline"]["reviews"][0]))
    elif change == "unknown_review":
        workspace["baseline"]["reviews"][0]["case_id"] = "unknown"
    elif change == "missing_answer":
        workspace["baseline"]["responses"].pop()
    elif change == "duplicate_answer":
        workspace["baseline"]["responses"].append(deepcopy(workspace["baseline"]["responses"][0]))
    elif change == "unknown_replacement":
        workspace["candidate"]["responses"][0]["case_id"] = "unknown"
    elif change == "wrong_schema":
        workspace["schema_version"] = "saved-answer-workspace-v2"
    elif change == "invalid_review_kind":
        workspace["baseline"]["reviews"][0]["reviewer_kind"] = "unknown"
    elif change == "missing_reviewer":
        del workspace["baseline"]["reviews"][0]["reviewer"]
    elif change == "missing_note":
        del workspace["baseline"]["reviews"][0]["note"]
    with pytest.raises(ValueError):
        restored(workspace)
        restored(workspace, "candidate")


@pytest.mark.parametrize("batch", ["baseline", "candidate"])
def test_duplicate_json_fields_cannot_silently_discard_saved_reviews(batch):
    workspace, _, _ = fully_reviewed_workspace()
    raw = json.dumps(workspace)
    needle = '"reviews": ' + json.dumps(workspace[batch]["reviews"])
    assert raw.count(needle) == 1
    damaged = raw.replace(needle, needle + ', "reviews": []')
    with pytest.raises(ValueError, match="duplicate JSON fields"):
        read_review_workspace(damaged.encode())


@pytest.mark.parametrize(
    "location", ["dataset", "baseline_answers", "baseline_reviews", "candidate_answers", "candidate_reviews"]
)
def test_restore_rejects_case_ids_that_cannot_match_saved_review_controls(location):
    workspace, _, _ = fully_reviewed_workspace()
    rows = (
        workspace["dataset"]
        if location == "dataset"
        else workspace[location.split("_")[0]]["responses" if location.endswith("answers") else "reviews"]
    )
    rows[0]["case_id"] = " " + rows[0]["case_id"] + " "
    with pytest.raises(ValueError, match="without surrounding whitespace"):
        read_review_workspace(json.dumps(workspace).encode())
    with pytest.raises(ValueError, match="without surrounding whitespace"):
        evaluate_review_workspace(workspace)


def test_saved_answer_import_rejects_whitespace_ids_before_case_selection():
    sample = sample_review_workspace()
    sample["dataset"][0]["case_id"] = " sample-1 "
    sample["baseline"]["responses"][0]["case_id"] = " sample-1 "
    workspace = new_review_workspace(
        pd.DataFrame(sample["dataset"]),
        sample["sources"],
        sample["baseline"]["responses"],
        target_name=sample["target_name"],
        target_version=sample["baseline"]["target_version"],
        captured_at=sample["baseline"]["captured_at"],
        evidence_kind=sample["evidence_kind"],
    )
    with pytest.raises(ValueError, match="without surrounding whitespace"):
        evaluate_review_workspace(workspace)


def test_workspace_without_optional_reviews_still_restores_as_pending():
    workspace = sample_review_workspace()
    del workspace["baseline"]["reviews"]
    assert restored(workspace)["review_status"].eq("pending").all()
