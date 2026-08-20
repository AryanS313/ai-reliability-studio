from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from src import charts, config
from src.auth import AuthenticationError, authenticate_request
from src.automation import ScheduleDefinition, ingest_production_logs, quality_drift
from src.observability import JsonFormatter, MetricsRegistry, ObservabilityPolicy, health_check
from src.presentation import execution_summary, failure_presentation
from src.reporting import csv_report, html_report, json_report
from src.review import ReviewQueuePolicy, ReviewService, build_review_queue
from src.storage import SQLiteRepository
from src.suggestions import comparison_language, prompt_change_proposal, run_level_insight_summary


def _result_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "case-1",
                "question": "Can I get a refund?",
                "category": "Refund",
                "severity": "high",
                "prompt_name": prompt,
                "prompt_version": prompt,
                "model_name": "model-a",
                "target_type": "synthetic_mock",
                "target_version": "target-v1",
                "execution_status": "passed",
                "failure_type": failure,
                "failure_labels": [],
                "overall_score": score,
                "expected_answer_match_score": score,
                "source_retrieval_score": 1.0,
                "citation_correctness_score": score,
                "groundedness_score": score,
                "escalation_correctness_score": 1.0,
                "hallucination_risk": "High" if failure != "Passed" else "Low",
                "latency_ms": 25,
                "estimated_cost": 0.001,
                "retrieved_sources": '["Refund Policy"]',
                "actual_answer": "Contact person@example.com with token sk-secret-value-123456.",
                "evaluator_confidence": 0.5,
            }
            for prompt, score, failure in [("baseline", 0.5, "Citation Failure"), ("candidate", 0.9, "Passed")]
        ]
    )


def test_proxy_authentication_requires_trust_and_valid_identity(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    monkeypatch.setenv("AUTH_TRUSTED_PROXY", "true")
    monkeypatch.setenv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com")
    identity = authenticate_request(
        {"X-Auth-Subject": "oidc|123", "X-Auth-Email": "USER@example.com", "X-Auth-Name": "User"}
    )
    assert identity.subject == "oidc|123"
    assert identity.email == "user@example.com"
    with pytest.raises(AuthenticationError):
        authenticate_request({"X-Auth-Subject": "oidc|456", "X-Auth-Email": "user@outside.invalid"})
    monkeypatch.delenv("AUTH_TRUSTED_PROXY")
    with pytest.raises(AuthenticationError, match="trusted proxy"):
        authenticate_request({"X-Auth-Subject": "oidc|123", "X-Auth-Email": "user@example.com"})


def test_single_user_authentication_is_refused_in_production(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    monkeypatch.setattr(config, "APP_ENV", "production")
    with pytest.raises(AuthenticationError):
        authenticate_request()


def test_log_ingestion_drift_and_schedule_validation_redact_sensitive_data():
    records = ingest_production_logs(
        [{"email": "person@example.com", "api_key": "sk-secret-value-123456", "score": 0.7}]
    )
    assert "person@example.com" not in records[0]["email"]
    assert records[0]["api_key"] == "[REDACTED]"
    assert quality_drift([0.9, 0.8], [0.6, 0.7])["regression"] is True
    assert quality_drift([], [0.7])["available"] is False
    with pytest.raises(ValueError):
        ScheduleDefinition("", enabled=True)


def test_observability_has_structured_redacted_logs_metrics_and_health():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "ars",
        logging.INFO,
        __file__,
        1,
        "finished for person@example.com using secret://PROVIDER_TOKEN",
        (),
        None,
    )
    record.structured_fields = {
        "api_key": "sk-secret-value-123456",
        "cookie": "session=private-cookie",
        "authorization": "secret://PROVIDER_TOKEN",
        "run_id": 7,
        "correlation_id": "correlation-8",
        "error_code": "provider_timeout",
    }
    payload = json.loads(formatter.format(record))
    assert payload["api_key"] == "[REDACTED]"
    assert payload["cookie"] == "[REDACTED]"
    assert payload["authorization"] == "[REDACTED]"
    assert "person@example.com" not in payload["message"]
    assert "PROVIDER_TOKEN" not in payload["message"]
    assert payload["run_id"] == 7
    assert payload["correlation_id"] == "correlation-8"
    assert payload["error_category"] == "provider_error"
    now = datetime(2026, 8, 20, tzinfo=UTC)
    policy = ObservabilityPolicy(retention_days=14, max_message_characters=12)
    assert policy.cutoff(now=now) == now - timedelta(days=14)
    assert len(json.loads(JsonFormatter(policy=policy).format(record))["message"]) <= 12
    with pytest.raises(ValueError):
        ObservabilityPolicy(retention_days=-1)
    registry = MetricsRegistry()
    registry.increment("runs")
    with registry.duration("latency_ms"):
        pass
    snapshot = registry.snapshot()
    assert snapshot["counters"]["runs"] == 1
    assert snapshot["gauges"]["latency_ms"] >= 0

    class Healthy:
        def migrate(self):
            return None

    class Unhealthy:
        def migrate(self):
            raise RuntimeError("database secret should not escape")

    assert health_check(Healthy())["status"] == "healthy"
    assert health_check(Unhealthy()) == {
        "status": "unhealthy",
        "application_version": config.APPLICATION_VERSION if hasattr(config, "APPLICATION_VERSION") else "1.0.0",
        "database": "unavailable",
    }


def test_reports_redact_secrets_and_pii_and_charts_separate_candidates():
    rows = _result_rows()
    json_value = json_report(rows, redact_personal_data=True)
    csv_value = csv_report(rows, redact_personal_data=True)
    html_value = html_report(rows, redact_personal_data=True)
    for report in [json_value, csv_value, html_value]:
        assert "person@example.com" not in report
        assert "sk-secret-value-123456" not in report
    payload = json.loads(json_value)
    assert payload["schema_version"] == "2.0"
    assert payload["metadata"]["evidence_classification"] == "synthetic"
    assert payload["metadata"]["execution_counts"]["total_executions"] == 2
    assert "Candidate verdicts" in html_value
    summary = charts.metric_summary(rows)
    assert summary["total_questions"] == 1
    assert summary["total_executions"] == 2
    assert len(summary["candidate_verdicts"]) == 2
    assert charts.prompt_comparison_chart(rows).data
    assert charts.model_comparison_chart(rows).data
    assert charts.category_score_chart(rows).data
    assert charts.failure_distribution_chart(rows).data
    assert charts.hallucination_distribution_chart(rows).data
    assert charts.latency_chart(rows).data
    assert charts.cost_chart(rows).data
    assert len(charts.prompt_metric_table(rows)) == 2


def test_reports_prevent_csv_injection_and_include_required_provenance():
    rows = _result_rows().assign(
        run_id=12,
        candidate_id="candidate-immutable-id",
        provider="openai",
        dataset_version="dataset-v2",
        knowledge_base_version="kb-v3",
        evaluator_version="deterministic-v3",
        threshold_version="threshold-v1",
        gate_configuration_version="gates-v1",
        environment="test",
        human_review_status="pending",
    )
    rows.loc[0, "question"] = '=HYPERLINK("https://attacker.invalid")'
    rows.loc[0, "actual_answer"] = "Use secret://PRIVATE_PROVIDER_TOKEN"
    csv_value = csv_report(rows)
    assert "'=HYPERLINK" in csv_value
    assert "PRIVATE_PROVIDER_TOKEN" not in csv_value
    metadata = json.loads(json_report(rows))["metadata"]
    assert metadata["run_ids"] == ["12"]
    assert metadata["candidate_ids"] == ["candidate-immutable-id"]
    assert metadata["dataset_versions"] == ["dataset-v2"]
    assert metadata["knowledge_base_versions"] == ["kb-v3"]
    assert metadata["human_review_status"] == ["pending"]


def test_run_completion_wording_and_layered_failure_presentation_are_safe():
    successful = _result_rows().assign(target_type="foundation_model", attempt_count=1)
    summary = execution_summary(successful)
    assert "all target calls completed" in summary["message"]
    assert "excluded from quality scoring" not in summary["message"]

    with_error = successful.copy()
    with_error.loc[0, "execution_status"] = "timed_out"
    with_error.loc[0, "attempt_count"] = 3
    error_summary = execution_summary(with_error)
    assert "1 infrastructure errors were excluded from quality scoring" in error_summary["message"]
    assert error_summary["retries"] == 2

    detail = failure_presentation(
        {
            "case_id": "case-1",
            "failure_type": "Privacy Violation",
            "failure_labels": ["privacy_violation"],
            "failure_reason_codes": ["pii_email_format"],
            "expected_answer": "Do not reveal private data.",
            "actual_answer": "Email person@example.com and use token sk-secret-value-123456.",
            "retrieved_chunks": [{"source_name": "Policy", "chunk_text": "Contact person@example.com"}],
            "evaluator_confidence": 0.5,
            "calibration_status": "insufficiently_calibrated",
            "final_prompt": "Authorization: Bearer top-secret-token-value",
        }
    )
    rendered = json.dumps(detail)
    assert "person@example.com" not in rendered
    assert "sk-secret-value-123456" not in rendered
    assert "top-secret-token-value" not in rendered
    assert detail["why_failed"].startswith("Labels:")
    assert detail["limitations"]


def test_review_queue_comments_resolution_and_evaluator_accuracy(tmp_path):
    repository = SQLiteRepository(tmp_path / "review.sqlite3")
    context = repository.create_workspace("reviewer@example.com", "Review")
    run_id = repository.create_run(
        context,
        run_name="review run",
        model_name="model",
        mode="batch",
        unique_case_count=1,
        total_executions=1,
    )
    repository.save_result(
        context,
        run_id,
        {
            "case_id": "case-1",
            "question": "Question",
            "actual_answer": "Answer",
            "execution_status": "passed",
            "failure_type": "Passed",
            "prompt_version": "prompt-v1",
            "target_version": "target-v1",
            "overall_score": 0.9,
            "failure_labels": [],
        },
    )
    with repository.connection() as conn:
        execution_id = int(conn.execute("SELECT id FROM executions").fetchone()["id"])
    service = ReviewService(repository)
    assignment_id = service.assign(context, execution_id, reviewer_id=context.user_id, reason="low confidence")
    assert service.add_comment(context, execution_id, "Reviewed exact source support.") > 0
    service.resolve(
        context,
        assignment_id,
        human_score=0.8,
        decision="acceptable",
        disagrees_with_automated=True,
    )
    accuracy = service.evaluator_accuracy(context)
    assert accuracy["reviewed"] == 1
    assert accuracy["agreement_rate"] == 0
    queue = build_review_queue(_result_rows(), ReviewQueuePolicy(random_sample_rate=0))
    assert len(queue) == 2
    assert "low_evaluator_confidence" in queue.iloc[0]["review_reasons"]


def test_prompt_proposals_are_failure_motivated_and_never_self_promote():
    rows = _result_rows()
    proposal = prompt_change_proposal("Be helpful.", rows, "fintech support")
    assert proposal["motivated_by_failures"]
    assert "requires evaluation before promotion" in proposal["label"]
    insight = run_level_insight_summary(rows, top_k=3)
    assert "Tie (synthetic workflow only)" in insight
    assert "Recommended next step" in insight


def test_comparison_language_handles_ties_unequal_cases_and_evidence_classes():
    rows = _result_rows().assign(target_type="foundation_model")
    rows["overall_score"] = 0.8
    tied = comparison_language(rows)
    assert tied["status"] == "tie"
    assert tied["summary"].startswith("Tie:")

    near = rows.copy()
    near.loc[near["prompt_name"] == "candidate", "overall_score"] = 0.803
    assert comparison_language(near)["status"] == "near_tie"

    unequal = pd.concat(
        [
            rows,
            pd.DataFrame(
                [
                    {
                        **rows.iloc[0].to_dict(),
                        "case_id": "case-2",
                        "prompt_name": "baseline",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    assert comparison_language(unequal)["status"] == "unequal_case_sets"

    mixed = rows.copy()
    mixed.loc[mixed["prompt_name"] == "baseline", "target_type"] = "synthetic_mock"
    assert comparison_language(mixed)["status"] == "incomparable_evidence"
