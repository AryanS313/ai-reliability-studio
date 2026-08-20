from __future__ import annotations

import json

import pandas as pd

from src import database
from src.chunker import chunk_documents
from src.domain import ExecutionStatus, TargetResponse, TargetType
from src.evaluator import run_evaluation
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
    _, _, project, chunks = _repository(tmp_path)
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
