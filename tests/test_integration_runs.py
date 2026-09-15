from __future__ import annotations

import json

import pandas as pd
import pytest

from src import database
from src.aggregation import evaluate_candidate
from src.calibration import DEFAULT_CALIBRATION_LABELS, EvaluatorThresholdConfiguration, calibrate_evaluators
from src.chunker import chunk_documents
from src.domain import ExecutionStatus, TargetResponse, TargetType
from src.evaluator import run_evaluation
from src.provenance import evidence_frame
from src.reporting import json_report
from src.scoring import EVALUATOR_VERSION, LABEL_SEMANTICS_VERSION
from src.storage import SQLiteRepository
from src.targets import ExternalHTTPTarget, ExternalTargetConfig, SecretResolver, TargetAdapter


def _dataset() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "refund-1",
                "question": "Are refunds eligible after 30 days?",
                "category": "Refund",
                "expected_behavior": "answer",
                "severity": "critical",
                "tags": ["negation"],
                "expected_answer": "Refunds are not eligible after 30 days unless fraud is suspected.",
                "expected_source": "Refund Policy",
                "should_escalate": False,
            }
        ]
    )


def _chunks():
    documents = [
        {
            "filename": "refund_policy.md",
            "text": "Refunds are not eligible after 30 days unless fraud is suspected.",
        }
    ]
    return documents, chunk_documents(documents, chunk_size_words=20, overlap_words=2)


def _repository(tmp_path):
    repository = SQLiteRepository(tmp_path / "integration.sqlite3")
    database.set_repository(repository)
    context = repository.local_context()
    project = repository.create_project(context, {"name": "Integration"})
    documents, chunks = _chunks()
    repository.save_documents_and_chunks(context, documents, chunks, project)
    return repository, context, project, chunks


def test_complete_mock_run_is_synthetic_and_candidates_are_separate(tmp_path):
    repository, context, project, chunks = _repository(tmp_path)
    results = run_evaluation(
        _dataset(),
        chunks,
        {"Current": "Be helpful", "Candidate": "Answer only using context"},
        "mock-model",
        2,
        0.01,
        3500,
        0.03,
        "comparison",
        project_id=project,
        max_concurrency=1,
    )
    assert len(results) == 2
    assert set(results["target_type"]) == {"synthetic_mock"}
    assert results.groupby("prompt_name")["actual_answer"].first().nunique() == 1
    runs = repository.list_runs(context)
    assert len(runs) == 2
    assert all(run["total_executions"] == 1 and run["unique_case_count"] == 1 for run in runs)


class DirectMockedProvider(TargetAdapter):
    target_type = TargetType.FOUNDATION_MODEL

    @property
    def version(self) -> str:
        return "provider-mocked-v1"

    def execute(self, request: dict) -> TargetResponse:
        chunk = request["retrieved_chunks"][0]
        return TargetResponse(
            status=ExecutionStatus.PASSED,
            answer=(
                "Refunds are not eligible after 30 days unless fraud is suspected.\n"
                f"Citation: [source:Refund Policy chunk:{chunk['chunk_id']}]"
            ),
            escalation={"should_escalate": False, "reason": "Factual policy answer"},
            latency_ms=20,
            input_tokens=20,
            output_tokens=15,
            cost=0.001,
            provider="mocked-provider",
            model="provider-model",
        )


def test_direct_provider_run_using_mocked_provider_response(tmp_path):
    _, _, project, chunks = _repository(tmp_path)
    results = run_evaluation(
        _dataset(),
        chunks,
        {"Current": "Policy prompt"},
        "provider-model",
        1,
        0.01,
        3500,
        0.03,
        "direct",
        project_id=project,
        target_adapter=DirectMockedProvider(),
        max_concurrency=1,
    )
    assert results.iloc[0]["execution_status"] == "passed"
    assert results.iloc[0]["model_name"] == "provider-model"
    assert results.iloc[0]["provider"] == "mocked-provider"
    assert results.iloc[0]["response_reported_provider"] == "mocked-provider"
    assert results.iloc[0]["configured_runner_model"] == "provider-model"
    assert results.iloc[0]["overall_score"] > 0.5


class FakeResponse:
    status = 200

    def read(self):
        return json.dumps(
            {
                "answer": "Refunds are not eligible after 30 days unless fraud is suspected. Source: Refund Policy",
                "escalation": {"should_escalate": False, "reason": "Policy answer"},
            }
        ).encode()


def test_external_http_target_run(tmp_path):
    repository, context, project, chunks = _repository(tmp_path)
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="external",
            endpoint="https://assistant.example.test/chat",
            headers={},
            request_template={"input": "${question}"},
            response_mappings={"answer": "$.answer", "escalation": "$.escalation"},
        ),
        SecretResolver(),
        opener=lambda request, timeout: FakeResponse(),
    )
    results = run_evaluation(
        _dataset(),
        chunks,
        {"Current": "Policy prompt"},
        "external-assistant",
        1,
        0.01,
        3500,
        0.03,
        "external",
        project_id=project,
        target_adapter=target,
        max_concurrency=1,
    )
    assert results.iloc[0]["execution_status"] == "passed"
    assert results.iloc[0]["target_type"] == "external_api"

    assert results.iloc[0]["provider"] is None
    assert results.iloc[0]["model_name"] is None
    assert results.iloc[0]["configured_runner_model"] == "external-assistant"
    assert results.iloc[0]["manifest"]["model"]["identifier"] is None
    assert results.iloc[0]["manifest"]["model"]["provider"] is None
    assert results.iloc[0]["manifest"]["model"]["provenance"] == "configured_runner_settings"
    assert results.iloc[0]["model_identity_provenance"] == "not_reported"
    assert repository.list_runs(context)[0]["model_name"] == "unknown"
    with repository.connection() as conn:
        execution = conn.execute("SELECT provider, model FROM executions").fetchone()
    assert execution["provider"] is None and execution["model"] is None


class RetryingProvider(DirectMockedProvider):
    calls = 0

    def execute(self, request):
        self.calls += 1
        if self.calls == 1:
            return TargetResponse(status=ExecutionStatus.RATE_LIMITED, provider="mocked-provider")
        return super().execute(request)


def test_result_provenance_and_retries_survive_storage_and_redacted_export(tmp_path):
    repository, context, project, chunks = _repository(tmp_path)
    result = run_evaluation(
        _dataset(),
        chunks,
        {"Current": "Policy prompt"},
        "provider-model",
        1,
        0.01,
        3500,
        0.03,
        "direct",
        project_id=project,
        target_adapter=RetryingProvider(),
        max_concurrency=1,
    )
    assert result.iloc[0]["attempt_count"] == 2
    assert result.iloc[0]["estimated_cost"] is None
    assert result.iloc[0]["metadata"]["last_attempt_cost_usd"] == 0.001
    assert result.iloc[0]["run_id"] > 0
    stored = evidence_frame(pd.DataFrame(repository.list_results(context)))
    assert stored.iloc[0]["attempt_count"] == 2
    assert stored.iloc[0]["dataset_version"] == result.iloc[0]["dataset_version"]
    assert stored.iloc[0]["provider"] == "mocked-provider"
    report = json.loads(json_report(stored))
    assert report["metadata"]["dataset_versions"] == [result.iloc[0]["dataset_version"]]
    assert report["metadata"]["knowledge_base_versions"]
    assert report["metadata"]["execution_counts"]["retries"] == 1
    assert report["metadata"]["run_ids"] == [str(result.iloc[0]["run_id"])]


class WithheldCredentialResponse(DirectMockedProvider):
    def execute(self, request):
        return TargetResponse(
            status=ExecutionStatus.INVALID_RESPONSE,
            error_code="credential_in_provider_response",
            metadata={"credential_redacted": True, "quality_score_eligible": False},
        )


def test_withheld_credential_disclosure_blocks_even_without_quality_scores(tmp_path):
    repository, context, project, chunks = _repository(tmp_path)
    result = run_evaluation(
        _dataset(),
        chunks,
        {"Current": "Policy prompt"},
        "provider-model",
        1,
        0.01,
        3500,
        0.03,
        "direct",
        project_id=project,
        target_adapter=WithheldCredentialResponse(),
        max_concurrency=1,
    )
    assert result.iloc[0]["execution_status"] == "invalid_response"
    assert "overall_score" not in result
    assert "privacy_violation" in result.iloc[0]["failure_labels"]
    assert "runtime_credential_disclosure" in result.iloc[0]["failure_reason_codes"]
    verdict = evaluate_candidate(result)
    assert verdict["verdict"] == "Not Ready"
    assert verdict["launch_blocked"] is True
    stored = evidence_frame(pd.DataFrame(repository.list_results(context)))
    assert stored.iloc[0]["expected_answers"] == result.iloc[0]["expected_answers"]
    assert stored.iloc[0]["expected_behavior"] == "answer"


def test_full_sample_has_honest_successes_review_findings_and_execution_errors(tmp_path):
    from src.sample_data import default_prompts, load_sample_documents, load_sample_eval_dataset

    repository, _, project, _ = _repository(tmp_path)
    _, chunks = load_sample_documents()
    dataset = load_sample_eval_dataset()
    results = run_evaluation(
        dataset,
        chunks,
        {"Current": default_prompts()["Current Prompt"]},
        "mock-model",
        3,
        0.05,
        3500,
        0.03,
        "sample",
        project_id=project,
        max_retries=0,
    )
    assert len(results) == len(dataset) == 32
    assert results["failure_type"].eq("Passed").sum() >= 8
    assert results["failure_type"].eq("Needs Review").any()
    assert results["failure_type"].eq("Execution Error").sum() == 3
    assert results["expected_behavior"].ne("").all()
    assert results.loc[results["case_id"].eq("synthetic-success"), "failure_type"].iloc[0] == "Passed"
    assert evaluate_candidate(results)["launch_blocked"] is True


class ReportedIdentityResponse(FakeResponse):
    def read(self):
        payload = json.loads(super().read())
        payload.update({"provider": "reported-vendor", "model": "deployed-assistant-v9"})
        return json.dumps(payload).encode()


def test_external_response_identity_is_preserved_separately_from_runner_defaults(tmp_path):
    repository, context, project, chunks = _repository(tmp_path)
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="support-assistant",
            endpoint="https://assistant.example.test/chat",
            headers={},
            request_template={"input": "${question}"},
            response_mappings={
                "answer": "$.answer",
                "escalation": "$.escalation",
                "provider": "$.provider",
                "model": "$.model",
            },
        ),
        SecretResolver(),
        opener=lambda request, timeout: ReportedIdentityResponse(),
    )
    results = run_evaluation(
        _dataset(),
        chunks,
        {"Current": "Policy prompt"},
        "mock-model",
        1,
        0.01,
        3500,
        0.03,
        "external",
        project_id=project,
        target_adapter=target,
        max_concurrency=1,
    )
    row = results.iloc[0]
    assert row["model_name"] == row["response_reported_model"] == "deployed-assistant-v9"
    assert row["provider"] == row["response_reported_provider"] == "reported-vendor"
    assert row["configured_runner_model"] == "mock-model"
    assert row["manifest"]["model"]["configured_runner_model"] == "mock-model"
    assert row["manifest"]["model"]["identifier"] is None
    assert row["manifest"]["model"]["runner_controls_model"] is False
    assert row["manifest"]["model"]["token_limit"] is None
    assert "mock-model" not in row["candidate_name"]
    with repository.connection() as conn:
        execution = conn.execute("SELECT provider, model FROM executions").fetchone()
    assert execution["provider"] == "reported-vendor"
    assert execution["model"] == "deployed-assistant-v9"
    persisted = repository.list_results(context)[0]
    identity = json.loads(persisted["metadata_json"])["model_identity"]
    assert identity["reported_provider"] == row["response_reported_provider"]
    assert identity["reported_model"] == row["response_reported_model"]
    assert identity["configured_runner_model"] == "mock-model"
    assert identity["provenance"] == "target_response"


def _qualified_result(evaluator_version=EVALUATOR_VERSION):
    rows = pd.DataFrame(
        [
            {
                "case_id": f"review-{index}",
                "split": "holdout",
                "human_labels": list(DEFAULT_CALIBRATION_LABELS) if index < 10 else [],
                "automatic_labels": list(DEFAULT_CALIBRATION_LABELS) if index < 10 else [],
            }
            for index in range(40)
        ]
    )
    return calibrate_evaluators(
        rows,
        labels=DEFAULT_CALIBRATION_LABELS,
        evaluator_version=evaluator_version,
        label_semantics_version=LABEL_SEMANTICS_VERSION,
    )


@pytest.mark.parametrize("version", ["deterministic-v3", None])
def test_run_rejects_stale_or_unbound_qualifying_calibration_before_target_execution(tmp_path, version):
    repository, context, project, chunks = _repository(tmp_path)
    calibration = _qualified_result("deterministic-v3")
    if version is None:
        calibration.pop("evaluator_version")
    assert calibration["threshold_version"] == EvaluatorThresholdConfiguration().version
    with pytest.raises(ValueError, match="evaluator version"):
        run_evaluation(
            _dataset(),
            chunks,
            {"Current": "Policy prompt"},
            "provider-model",
            1,
            0.01,
            3500,
            0.03,
            "direct",
            project_id=project,
            target_adapter=DirectMockedProvider(),
            max_concurrency=1,
            calibration_result=calibration,
        )
    assert repository.list_runs(context) == []


def test_run_records_current_version_bound_calibration_in_manifest_and_rows(tmp_path):
    repository, context, project, chunks = _repository(tmp_path)
    calibration = _qualified_result()
    results = run_evaluation(
        _dataset(),
        chunks,
        {"Current": "Policy prompt"},
        "provider-model",
        1,
        0.01,
        3500,
        0.03,
        "direct",
        project_id=project,
        target_adapter=DirectMockedProvider(),
        max_concurrency=1,
        calibration_result=calibration,
    )
    assert results.iloc[0]["calibration_status"] == "calibrated"
    assert results.iloc[0]["calibration_version"] == calibration["calibration_version"]
    entry = next(
        item for item in results.iloc[0]["manifest"]["evaluators"] if item["name"] == "human_review_calibration"
    )
    assert entry["evaluator_version"] == EVALUATOR_VERSION
    assert entry["label_semantics_version"] == LABEL_SEMANTICS_VERSION
    assert repository.list_runs(context)[0]["calibration_version"] == calibration["calibration_version"]
