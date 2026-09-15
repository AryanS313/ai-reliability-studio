from __future__ import annotations

import json

import pandas as pd
import pytest

from src.aggregation import LaunchGateConfig, evaluate_candidate
from src.reporting import json_report
from src.saved_responses import (
    apply_response_reviews,
    compare_response_reviews,
    evaluate_saved_responses,
    read_response_file,
)
from src.versioning import version_hash


def material(count=3):
    policy = "Account records are retained for 10 days."
    chunks = [
        {
            "chunk_id": "records-1",
            "document_id": "records",
            "document_version": "v1",
            "source_name": "Records Policy",
            "chunk_text": policy,
        }
    ]
    dataset = pd.DataFrame(
        [
            {
                "case_id": f"case-{index}",
                "question": "How long are account records retained?",
                "expected_answer": policy,
                "expected_source": "Records Policy",
                "category": "Records",
                "should_escalate": False,
            }
            for index in range(count)
        ]
    )
    responses = [
        {
            "case_id": f"case-{index}",
            "actual_answer": policy,
            "citations": [{"chunk_id": "records-1"}],
            "escalation": {"should_escalate": False},
        }
        for index in range(count)
    ]
    return dataset, responses, chunks


def evaluate(dataset, responses, chunks, **kwargs):
    return evaluate_saved_responses(
        dataset,
        responses,
        chunks,
        target_name="Review fixture",
        target_version=kwargs.pop("target_version", "baseline"),
        captured_at="2026-09-07T10:00:00+00:00",
        evidence_kind="fixture",
        **kwargs,
    )


def reviews_for(df, decision="supported"):
    return [
        {
            "case_id": row["case_id"],
            "response_hash": row["response_hash"],
            "case_version": row["case_version"],
            "knowledge_base_version": row["knowledge_base_version"],
            "decision": decision,
            "reviewer": "Fixture author",
            "reviewer_kind": "ai_assisted",
            "note": "Checked against Records Policy, records-1.",
        }
        for row in df.to_dict(orient="records")
    ]


def test_client_answers_remain_pending_and_unknown_measurements_are_not_filled():
    dataset, responses, chunks = material()
    result = evaluate(dataset, responses, chunks)
    assert len(result) == 3
    assert result["review_status"].tolist() == ["pending"] * 3
    assert result["source_retrieval_score"].isna().all()
    assert result["latency_ms"].isna().all()
    assert result["estimated_cost"].isna().all()
    assert all(not value["available"] for value in result["retrieval_metrics"])
    assert evaluate_candidate(result, LaunchGateConfig(require_calibration=False))["launch_blocked"] is True
    report = json.loads(json_report(result))
    assert report["metadata"]["run_ids"]
    assert report["metadata"]["dataset_versions"]
    assert report["metadata"]["knowledge_base_versions"]
    assert report["metadata"]["threshold_versions"]
    assert report["metadata"]["evidence_classification"] == "synthetic_fixture"


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_response_set_must_match_requested_case_set(mutation):
    dataset, responses, chunks = material()
    if mutation == "missing":
        responses.pop()
    elif mutation == "extra":
        responses.append({**responses[0], "case_id": "unexpected"})
    else:
        responses.append(responses[0])
    with pytest.raises(ValueError):
        evaluate(dataset, responses, chunks)


def test_reviews_bind_to_response_expectation_and_source_versions():
    dataset, responses, chunks = material()
    result = evaluate(dataset, responses, chunks)
    reviews = reviews_for(result)
    reviewed = apply_response_reviews(result, reviews)
    assert reviewed["review_status"].eq("reviewed").all()
    assert reviewed["human_review_status"].eq("ai_assisted_review_only").all()
    assert result["review_status"].eq("pending").all()
    for field in ("response_hash", "case_version", "knowledge_base_version"):
        invalid = [{**reviews[0], field: "stale"}]
        with pytest.raises(ValueError, match=field):
            apply_response_reviews(result, invalid)


def test_redacted_manifest_verifies_without_changing_original_input_identity():
    dataset, responses, chunks = material(1)
    chunks[0]["chunk_text"] += " Test credential: sk-fictionalfixture0123456789. Contact reviewer@example.test."
    raw_source_hash = version_hash(chunks)
    result = evaluate(dataset, responses, chunks)
    report = json.loads(json_report(result))
    exported = report["run_manifests"][0]
    assert exported["original_hash_status"] == "verified"
    assert exported["redacted"] is True
    assert result.iloc[0]["knowledge_base_version"] == raw_source_hash
    assert exported["manifest"]["knowledge_base"]["content_hash"] == raw_source_hash
    assert "sk-fictionalfixture0123456789" not in json.dumps(report)
    assert "reviewer@example.test" not in json.dumps(report)


def test_thirty_case_baseline_and_ten_case_retest_keep_review_transitions_separate():
    dataset, responses, chunks = material(30)
    baseline = evaluate(dataset, responses, chunks)
    baseline_reviews = reviews_for(baseline, "failed")
    baseline_reviews[9]["decision"] = "supported"
    baseline = apply_response_reviews(baseline, baseline_reviews)
    changed = [{**row, "actual_answer": row["actual_answer"] + " This response was revised."} for row in responses[:10]]
    candidate = evaluate(dataset.iloc[:10].copy(), changed, chunks, target_version="revised")
    candidate_reviews = reviews_for(candidate)
    candidate_reviews[8]["decision"] = "failed"
    candidate_reviews[9]["decision"] = "failed"
    candidate = apply_response_reviews(candidate, candidate_reviews)
    comparison = compare_response_reviews(baseline, candidate)
    assert comparison["baseline_case_count"] == 30
    assert comparison["candidate_case_count"] == 10
    assert comparison["counts"] == {"resolved": 8, "unchanged": 1, "regressed": 1}
    assert len(baseline) == 30


def test_comparison_refuses_unreviewed_or_changed_source_evidence():
    dataset, responses, chunks = material()
    baseline = evaluate(dataset, responses, chunks)
    pending = compare_response_reviews(baseline, baseline)
    assert pending["counts"] == {"pending_review": 3}
    reviewed = apply_response_reviews(baseline, reviews_for(baseline))
    changed = reviewed.copy(deep=True)
    changed["knowledge_base_version"] = "different-policy"
    comparison = compare_response_reviews(reviewed, changed)
    assert comparison["counts"] == {"not_comparable": 3}


def test_sparse_optional_expectations_do_not_change_case_identity_in_retest():
    dataset, responses, chunks = material(2)
    records = dataset.to_dict(orient="records")
    records[1]["expected_answers"] = [records[1]["expected_answer"]]
    records[1]["expected_sources"] = [records[1]["expected_source"]]
    records[1]["notes"] = "Other case metadata."
    baseline = evaluate(pd.DataFrame(records), responses, chunks)
    candidate = evaluate(pd.DataFrame([records[0]]), responses[:1], chunks, target_version="retest")
    assert baseline.iloc[0]["case_version"] == candidate.iloc[0]["case_version"]
    baseline = apply_response_reviews(baseline, reviews_for(baseline))
    candidate = apply_response_reviews(candidate, reviews_for(candidate))
    assert compare_response_reviews(baseline, candidate)["counts"] == {"unchanged": 1}


def test_changed_review_alone_is_not_a_resolved_answer_and_fixture_cannot_match_client():
    dataset, responses, chunks = material(1)
    evaluated = evaluate(dataset, responses, chunks)
    failed = apply_response_reviews(evaluated, reviews_for(evaluated, "failed"))
    supported = apply_response_reviews(evaluated, reviews_for(evaluated, "supported"))
    assert compare_response_reviews(failed, supported)["counts"] == {"review_decision_changed": 1}
    supported["evidence_kind"] = "client_supplied"
    assert compare_response_reviews(failed, supported)["counts"] == {"not_comparable": 1}


def test_execution_errors_cannot_be_scored_or_reviewed_as_answer_quality():
    dataset, responses, chunks = material(1)
    responses[0].update({"actual_answer": "", "execution_status": "timed_out"})
    result = evaluate(dataset, responses, chunks)
    assert result["overall_score"].isna().all()
    with pytest.raises(ValueError, match="Execution errors"):
        apply_response_reviews(result, reviews_for(result, "supported"))
    reviewed = apply_response_reviews(result, reviews_for(result, "execution_error"))
    assert reviewed.iloc[0]["review_decision"] == "execution_error"


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "invalid"])
def test_invalid_client_measurements_are_rejected(value):
    dataset, responses, chunks = material(1)
    responses[0]["latency_ms"] = value
    with pytest.raises(ValueError, match="latency_ms"):
        evaluate(dataset, responses, chunks)


def test_parsing_is_bounded_and_rejects_ambiguous_csv_headers():
    rows = [{"case_id": "case-1", "actual_answer": "Answer"}]
    assert read_response_file("responses.json", json.dumps(rows).encode()) == rows
    assert read_response_file("responses.jsonl", (json.dumps(rows[0]) + "\n").encode()) == rows
    assert read_response_file("responses.csv", b"case_id,actual_answer\ncase-1,Answer\n") == rows
    with pytest.raises(ValueError, match="duplicate column"):
        read_response_file("responses.csv", b"case_id,case_id\nx,y\n")
    with pytest.raises(ValueError):
        read_response_file("responses.json", b'{"case_id":"case-1"}')
