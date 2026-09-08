from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from src import config, database
from src.calibration import EvaluatorThresholdConfiguration, uncalibrated_status, validate_calibration_for_run
from src.datasets import (
    LEGACY_REQUIRED_FIELDS,
    DatasetValidationException,
    dataset_quality_report,
    normalize_dataset_frame,
    strict_bool,
    validate_dataset_frame,
)
from src.document_loader import source_extraction_warnings
from src.domain import ExecutionStatus, TargetType
from src.execution import CancellationToken, ExecutionEngine, ExecutionPolicy
from src.judges import LLMJudge
from src.retrieval import retrieval_metrics, retrieve_chunks
from src.scoring import EVALUATOR_VERSION, LABEL_SEMANTICS_VERSION, score_result
from src.suggestions import suggestion_for_failure
from src.targets import (
    ExternalHTTPTarget,
    FoundationModelConfig,
    FoundationModelTarget,
    MockTargetConfig,
    SecretResolver,
    SyntheticMockTarget,
    TargetAdapter,
    target_configuration_for_storage,
)
from src.utils import format_context
from src.vector_store import SimpleVectorStore
from src.versioning import build_run_manifest, text_hash, version_hash

REQUIRED_COLUMNS = LEGACY_REQUIRED_FIELDS
EVALUATION_UPLOAD_TYPES = ["csv", "tsv", "xlsx", "xls", "json", "jsonl"]


def read_eval_dataset(filename: str, data: bytes) -> pd.DataFrame:
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError(f"Evaluation dataset exceeds the {config.MAX_UPLOAD_BYTES} byte upload limit.")
    suffix = Path(filename).suffix.lower()
    buffer = BytesIO(data)
    if suffix == ".csv":
        frame = pd.read_csv(buffer, dtype=str, keep_default_na=False)
    elif suffix == ".tsv":
        frame = pd.read_csv(buffer, sep="\t", dtype=str, keep_default_na=False)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(buffer, dtype=str, keep_default_na=False)
    elif suffix == ".json":
        frame = pd.read_json(buffer, dtype=False, convert_dates=False)
    elif suffix == ".jsonl":
        frame = pd.read_json(buffer, lines=True, dtype=False, convert_dates=False)
    else:
        raise ValueError(f"Unsupported evaluation dataset type: {suffix or 'no extension'}")
    if len(frame) > config.MAX_DATASET_ROWS:
        raise ValueError(f"Evaluation dataset has {len(frame)} rows; the limit is {config.MAX_DATASET_ROWS}.")
    return normalize_eval_dataset(frame)


def validate_eval_dataset(df: pd.DataFrame) -> None:
    errors = validate_dataset_frame(df, allow_legacy=True)
    if errors:
        raise DatasetValidationException(errors)


def parse_bool(value: Any) -> bool:
    parsed = strict_bool(value)
    assert parsed is not None
    return parsed


def normalize_eval_dataset(df: pd.DataFrame) -> pd.DataFrame:
    return normalize_dataset_frame(df, allow_legacy=True)


def run_evaluation(
    eval_df: pd.DataFrame,
    chunks: list[dict[str, Any]],
    prompts: dict[str, str],
    model_name: str | list[str],
    top_k: int,
    similarity_threshold: float,
    latency_threshold_ms: float,
    cost_threshold_usd: float,
    mode: str,
    project_id: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    api_key: str | None = None,
    *,
    target_adapter: TargetAdapter | None = None,
    cancellation_token: CancellationToken | None = None,
    max_concurrency: int = 4,
    max_retries: int | None = None,
    metric_weights: dict[str, float] | None = None,
    environment: str | None = None,
    judge_evaluator: LLMJudge | None = None,
    threshold_configuration: EvaluatorThresholdConfiguration | None = None,
    calibration_result: dict[str, Any] | None = None,
    candidate_tuned_on_dataset: bool = False,
) -> pd.DataFrame:
    dataset = normalize_eval_dataset(eval_df)
    threshold_configuration = threshold_configuration or EvaluatorThresholdConfiguration()
    calibration = calibration_result or uncalibrated_status(threshold_configuration)
    validate_calibration_for_run(
        calibration,
        threshold_configuration,
        evaluator_version=EVALUATOR_VERSION,
        label_semantics_version=LABEL_SEMANTICS_VERSION,
    )
    models = model_name if isinstance(model_name, list) else [model_name]
    vector_store = SimpleVectorStore()
    vector_store.build(chunks)
    context = database.current_context()
    repository = database.get_repository()
    snapshot_records = dataset.to_dict(orient="records")
    dataset_version_id = repository.create_dataset_version(
        context,
        project_id,
        "Evaluation Dataset",
        snapshot_records,
        immutable=True,
    )
    dataset_hash = version_hash(snapshot_records)
    document_versions = sorted(
        {
            str(chunk.get("document_hash") or chunk.get("document_version") or chunk.get("document_id") or "legacy")
            for chunk in chunks
        }
    )
    dataset_quality = dataset_quality_report(
        eval_df,
        available_sources={str(chunk.get("source_name") or "") for chunk in chunks},
        candidate_tuned_on_dataset=candidate_tuned_on_dataset,
    )
    total_steps = len(dataset) * len(prompts) * len(models)
    completed_steps = 0
    all_results: list[dict[str, Any]] = []
    cancellation_token = cancellation_token or CancellationToken()

    for selected_model in models:
        adapter = target_adapter or _adapter_for_model(selected_model, api_key)
        effective_retries = adapter.default_retry_count if max_retries is None else max_retries
        if isinstance(adapter, ExternalHTTPTarget):
            applies_prompt = adapter.sends_system_prompt
            if len(prompts) > 1 and not applies_prompt:
                raise ValueError(
                    "This external target's request template does not send ${system_prompt}. "
                    "Run one prompt, add the placeholder for an endpoint that accepts it, or compare saved answers "
                    "from separately deployed assistant versions."
                )
        target_type = adapter.target_type.value
        target_configuration = _target_storage_configuration(adapter)
        target_version_id = repository.create_target_version(
            context,
            project_id,
            f"{target_type}:{selected_model}",
            target_type,
            target_configuration,
        )
        for prompt_name, system_prompt in prompts.items():
            prompt_version_id = database.save_prompt(
                project_id,
                prompt_name,
                system_prompt,
                "candidate" if len(prompts) > 1 else "current",
                context=context,
            )
            prompt_hash = text_hash(system_prompt)
            target_name = _target_display_name(adapter, selected_model)
            candidate_id = version_hash(
                {
                    "prompt_version": prompt_hash,
                    "model_name": selected_model,
                    "target_version": adapter.version,
                    "target_type": target_type,
                }
            )
            controls_model = target_type in {TargetType.FOUNDATION_MODEL.value, TargetType.SYNTHETIC.value}
            configured_provider = (
                config.provider_for_model(selected_model)
                if target_type == TargetType.FOUNDATION_MODEL.value
                else "synthetic"
                if target_type == TargetType.SYNTHETIC.value
                else None
            )
            candidate_name = f"{prompt_name} · {target_name}" + (f" · {selected_model}" if controls_model else "")
            retrieval_configuration = {
                "top_k": top_k,
                "similarity_threshold": similarity_threshold,
                "retriever": "hybrid-v1",
                "embedding_provider": vector_store.embedder.name,
                "semantic_embeddings": vector_store.embedder.semantic,
            }
            manifest = build_run_manifest(
                prompt={"name": prompt_name, "version_id": prompt_version_id, "content_hash": prompt_hash},
                dataset={
                    "version_id": dataset_version_id,
                    "content_hash": dataset_hash,
                    "case_count": len(dataset),
                    "quality_report": dataset_quality,
                },
                documents=[
                    {
                        "version": value,
                        "extraction_notices": source_extraction_warnings(
                            [
                                chunk
                                for chunk in chunks
                                if str(
                                    chunk.get("document_hash")
                                    or chunk.get("document_version")
                                    or chunk.get("document_id")
                                    or "legacy"
                                )
                                == value
                            ]
                        ),
                    }
                    for value in document_versions
                ],
                retrieval=retrieval_configuration,
                target={
                    "type": target_type,
                    "version": adapter.version,
                    "version_id": target_version_id,
                    "execution_policy": {"max_concurrency": max_concurrency, "max_retries": effective_retries},
                    "system_prompt_application": (
                        "external_request_template" if applies_prompt else "not_sent_to_external_target"
                    )
                    if isinstance(adapter, ExternalHTTPTarget)
                    else "provider_system_instruction"
                    if isinstance(adapter, FoundationModelTarget)
                    else "ignored_by_synthetic_fixture"
                    if isinstance(adapter, SyntheticMockTarget)
                    else "adapter_defined",
                },
                evaluators=[
                    {
                        "name": "deterministic_rules",
                        "type": "deterministic_rules",
                        "version": EVALUATOR_VERSION,
                        "label_semantics_version": LABEL_SEMANTICS_VERSION,
                        "weights": metric_weights or {},
                        "threshold_version": threshold_configuration.version,
                        "thresholds": threshold_configuration.thresholds,
                    },
                    {
                        "name": "retrieval_similarity",
                        "type": "semantic_similarity" if vector_store.embedder.semantic else "lexical_similarity",
                        "version": retrieval_configuration["retriever"],
                    },
                    {
                        "name": "model_judge",
                        "type": "model_judge",
                        "version": (judge_evaluator.configuration.version if judge_evaluator is not None else None),
                        "enabled": judge_evaluator is not None,
                        "policy": "advisory_only",
                    },
                    {
                        "name": "human_review_calibration",
                        "type": "human_review",
                        "version": calibration.get("calibration_version"),
                        "status": calibration.get("status"),
                        "reviewed_cases": calibration.get("reviewed_cases", 0),
                        "evaluator_version": calibration.get("evaluator_version"),
                        "label_semantics_version": calibration.get("label_semantics_version"),
                    },
                ],
                model={
                    "provenance": "configured_runner_settings",
                    "provider": configured_provider,
                    "identifier": selected_model if controls_model else None,
                    "configured_runner_model": selected_model,
                    "runner_controls_model": controls_model,
                    "observed_identity_location": "per_execution_result",
                    "sampling_setting_semantics": "requested",
                    "effective_sampling_location": "per_execution_result.metadata.sampling"
                    if target_type == TargetType.FOUNDATION_MODEL.value and configured_provider == "anthropic"
                    else None,
                    "temperature": target_configuration.get("temperature", 0.0)
                    if target_type == TargetType.FOUNDATION_MODEL.value
                    else None,
                    "seed": target_configuration.get("seed", 17)
                    if target_type == TargetType.SYNTHETIC.value
                    else target_configuration.get("seed")
                    if target_type == TargetType.FOUNDATION_MODEL.value
                    else None,
                    "token_limit": target_configuration.get("max_tokens", 2048)
                    if target_type == TargetType.FOUNDATION_MODEL.value
                    else None,
                },
                user_id=context.user_id,
                workspace_id=context.workspace_id,
                environment=environment,
            )
            run_id = database.create_eval_run(
                run_name=f"{candidate_name} · {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                model_name=selected_model if controls_model else "unknown",
                mode=mode,
                total_questions=len(dataset),
                total_executions=len(dataset),
                project_id=project_id,
                notes=json.dumps(retrieval_configuration),
                target_type=target_type,
                target_version=adapter.version,
                dataset_version_id=dataset_version_id,
                manifest=manifest,
                evaluator_version=EVALUATOR_VERSION,
                label_semantics_version=LABEL_SEMANTICS_VERSION,
                threshold_version=threshold_configuration.version,
                calibration_status=str(calibration.get("status", "insufficiently_calibrated")),
                calibration_version=str(calibration.get("calibration_version") or "") or None,
                context=context,
            )
            requests: list[dict[str, Any]] = []
            rows_by_case: dict[str, dict[str, Any]] = {}
            for _, row in dataset.iterrows():
                case = row.to_dict()
                question = str(case["question"])
                retrieved = retrieve_chunks(
                    vector_store,
                    question,
                    top_k,
                    similarity_threshold,
                    metadata_filters=case.get("metadata_filters")
                    if isinstance(case.get("metadata_filters"), dict)
                    else None,
                )
                case_id = str(case["case_id"])
                request = {
                    **case,
                    "case_id": case_id,
                    "question": question,
                    "input": question,
                    "context": format_context(retrieved),
                    "system_prompt": system_prompt,
                    "retrieved_chunks": retrieved,
                    "prompt_version": prompt_hash,
                    "dataset_version": dataset_hash,
                    "document_versions": document_versions,
                    "retrieval_configuration": retrieval_configuration,
                    "evaluation_configuration": {"weights": metric_weights or {}},
                }
                requests.append(request)
                rows_by_case[case_id] = {"case": case, "retrieved": retrieved}

            engine = ExecutionEngine(
                adapter,
                ExecutionPolicy(max_concurrency=max_concurrency, max_retries=effective_retries),
            )

            progress_base = completed_steps

            def update_progress(done: int, total: int, _record, base: int = progress_base) -> None:
                if progress_callback:
                    progress_callback(base + done, total_steps)

            records = engine.run(requests, cancellation=cancellation_token, progress=update_progress)
            completed_steps += len(records)
            for record in records:
                case_bundle = rows_by_case[record.case_id]
                case = case_bundle["case"]
                retrieved = case_bundle["retrieved"]
                response = record.response
                result = _base_result(
                    case,
                    retrieved,
                    prompt_name,
                    prompt_hash,
                    selected_model,
                    target_type,
                    adapter.version,
                    record.status,
                )
                result.update(
                    {
                        "run_id": run_id,
                        "attempt_count": record.attempt_count,
                        "cache_hit": record.cache_hit,
                        "execution_key": record.execution_key,
                        "manifest": manifest,
                        "manifest_hash": manifest["manifest_hash"],
                        "run_timestamp": manifest["created_at"],
                        "environment": manifest["environment"],
                        "dataset_version": dataset_hash,
                        "document_versions": document_versions,
                        "knowledge_base_version": version_hash(document_versions),
                        "provider": response.provider if response else None,
                        "model_name": response.model if response else None,
                        "response_reported_provider": response.provider if response else None,
                        "response_reported_model": response.model if response else None,
                        "configured_runner_provider": configured_provider,
                        "configured_runner_model": selected_model,
                        "model_identity_provenance": "target_response"
                        if response and (response.provider or response.model)
                        else "not_reported",
                        "human_review_status": "not_reviewed",
                        "retrieval_metrics_scope": "evaluator_local_reference_retrieval",
                        "client_retrieval_status": "not_measured",
                        "evaluator_version": EVALUATOR_VERSION,
                        "label_semantics_version": LABEL_SEMANTICS_VERSION,
                        "threshold_version": threshold_configuration.version,
                        "calibration_status": calibration.get("status", "insufficiently_calibrated"),
                        "calibration_version": calibration.get("calibration_version"),
                        "dataset_quality_version": dataset_quality["version"],
                        "dataset_quality_status": (
                            "launch_eligible" if dataset_quality["launch_eligible"] else "insufficient"
                        ),
                        "dataset_launch_eligible": bool(dataset_quality["launch_eligible"]),
                        "candidate_id": candidate_id,
                        "candidate_name": candidate_name,
                        "target_name": target_name,
                    }
                )
                if response is None or record.status != ExecutionStatus.PASSED:
                    error_code = (
                        response.error_code if response else "cancelled"
                    ) or f"{record.status.value}_execution_failure"
                    status_value = record.status.value
                    result.update(
                        {
                            "actual_answer": "",
                            "latency_ms": response.latency_ms if response else 0.0,
                            "estimated_cost": response.cost if response else None,
                            "input_tokens": response.input_tokens if response else None,
                            "output_tokens": response.output_tokens if response else None,
                            "http_status": response.http_status if response else None,
                            "error_code": error_code,
                            "safe_error": response.safe_error if response else "Execution was cancelled.",
                            "failure_type": "Execution Error",
                            "failure_labels": ["infrastructure_failure"],
                            "failure_reason_codes": [f"infrastructure_{error_code}"],
                            "failure_evidence": {
                                "infrastructure_failure": [
                                    {
                                        "reason_code": f"infrastructure_{error_code}",
                                        "execution_status": status_value,
                                        "quality_score_eligible": False,
                                    }
                                ]
                            },
                            "hallucination_risk": "Not Scored",
                            "determination_state": "unable_to_determine",
                            "evaluator_confidence": 0.0,
                            "metadata": response.metadata if response else {},
                            "synthetic_prompt_ignored": bool(
                                response and response.metadata.get("prompt_content_ignored", False)
                            ),
                        }
                    )
                else:
                    expected_answer = str(
                        case.get("expected_answer") or (case["expected_answers"][0] if case["expected_answers"] else "")
                    )
                    judge_result = (
                        judge_evaluator.evaluate(
                            question=str(case["question"]),
                            expected_answer=expected_answer,
                            actual_answer=response.answer,
                            retrieved_chunks=retrieved,
                        )
                        if judge_evaluator is not None
                        else None
                    )
                    scores = score_result(
                        actual_answer=response.answer,
                        expected_answer=expected_answer,
                        expected_answers=list(case.get("expected_answers") or []),
                        unacceptable_answers=list(case.get("unacceptable_answers") or []),
                        expected_source=str(
                            case.get("expected_source")
                            or (case["expected_sources"][0] if case["expected_sources"] else "")
                        ),
                        should_escalate=bool(case.get("should_escalate")),
                        expected_destination=str(case.get("escalation_destination") or "") or None,
                        expected_urgency=str(case.get("escalation_urgency") or "") or None,
                        structured_escalation=response.escalation,
                        provided_citations=list(response.citations),
                        rubric=dict(case.get("rubric") or {}),
                        retrieved_chunks=retrieved,
                        latency_ms=response.latency_ms,
                        estimated_cost=float(response.cost or 0.0),
                        latency_threshold_ms=latency_threshold_ms,
                        cost_threshold_usd=cost_threshold_usd,
                        weights=metric_weights,
                        judge=judge_result,
                        evaluator_thresholds=threshold_configuration.thresholds,
                    )
                    retrieval = retrieval_metrics(
                        retrieved,
                        expected_sources=list(case.get("expected_sources") or []),
                        expected_passages=list(case.get("expected_passages") or []),
                    )
                    result.update(
                        {
                            "actual_answer": response.answer,
                            "latency_ms": response.latency_ms,
                            "estimated_cost": response.cost,
                            "input_tokens": response.input_tokens,
                            "output_tokens": response.output_tokens,
                            "http_status": response.http_status,
                            "final_prompt": response.final_prompt,
                            "metadata": response.metadata,
                            "synthetic_prompt_ignored": bool(response.metadata.get("prompt_content_ignored", False)),
                            "retrieval_metrics": retrieval,
                            **scores,
                        }
                    )
                    result["suggested_fix"] = suggestion_for_failure(result["failure_type"])
                result["metadata"] = {
                    **dict(result.get("metadata") or {}),
                    "execution": {
                        "attempt_count": record.attempt_count,
                        "cache_hit": record.cache_hit,
                        "execution_key": record.execution_key,
                        "max_retries": effective_retries,
                    },
                    "model_identity": {
                        "provenance": result["model_identity_provenance"],
                        "reported_provider": result["response_reported_provider"],
                        "reported_model": result["response_reported_model"],
                        "configured_runner_provider": configured_provider,
                        "configured_runner_model": selected_model,
                        "target_type": target_type,
                    },
                }
                result["execution_id"] = database.save_eval_result(run_id, result, context=context)
                all_results.append(result)
    return pd.DataFrame(all_results)


def run_single_test(
    question: str,
    expected_answer: str,
    expected_source: str,
    should_escalate: bool,
    chunks: list[dict[str, Any]],
    prompts: dict[str, str],
    model_name: str,
    top_k: int,
    similarity_threshold: float,
    latency_threshold_ms: float = 3500,
    cost_threshold_usd: float = 0.03,
    api_key: str | None = None,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "case_id": "single-test",
                "question": question,
                "category": "Single Test",
                "expected_behavior": "answer",
                "severity": "medium",
                "tags": ["single-test"],
                "expected_answer": expected_answer,
                "expected_source": expected_source,
                "should_escalate": should_escalate,
            }
        ]
    )
    return run_evaluation(
        frame,
        chunks,
        prompts,
        model_name,
        top_k,
        similarity_threshold,
        latency_threshold_ms,
        cost_threshold_usd,
        mode="single-test",
        api_key=api_key,
        max_concurrency=1,
    )


def _adapter_for_model(model_name: str, api_key: str | None) -> TargetAdapter:
    if model_name == "mock-model":
        return SyntheticMockTarget(MockTargetConfig())
    provider = config.provider_for_model(model_name)
    secret_name = f"session_{provider}_key"
    values = {secret_name: api_key} if api_key else {}
    return FoundationModelTarget(
        FoundationModelConfig(provider=provider, model=model_name, api_key_reference=f"secret://{secret_name}"),
        secrets=SecretResolver(values),
    )


def _target_storage_configuration(adapter: TargetAdapter) -> dict[str, Any]:
    configuration = getattr(adapter, "configuration", {})
    if hasattr(configuration, "__dataclass_fields__"):
        stored = target_configuration_for_storage(configuration)
        stored["version_hash"] = adapter.version
        if implementation := getattr(adapter, "implementation_version", None):
            stored["adapter_implementation_version"] = implementation
        return stored
    return {"adapter": type(adapter).__name__, "version_hash": adapter.version}


def _target_display_name(adapter: TargetAdapter, model_name: str) -> str:
    configuration = getattr(adapter, "configuration", None)
    configured_name = getattr(configuration, "name", None)
    if configured_name:
        return str(configured_name)
    if adapter.target_type == TargetType.SYNTHETIC:
        return "Deterministic Synthetic Scenarios"
    if adapter.target_type == TargetType.FOUNDATION_MODEL:
        provider = getattr(configuration, "provider", config.provider_for_model(model_name))
        return f"{str(provider).title()} Direct Model"
    return "External Assistant"


def _base_result(
    case: dict[str, Any],
    retrieved: list[dict[str, Any]],
    prompt_name: str,
    prompt_version: str,
    model_name: str,
    target_type: str,
    target_version: str,
    status: ExecutionStatus,
) -> dict[str, Any]:
    return {
        "case_id": str(case["case_id"]),
        "question": str(case["question"]),
        "expected_answer": str(case.get("expected_answer") or ""),
        "expected_source": str(case.get("expected_source") or ""),
        "retrieved_chunks": retrieved,
        "retrieved_sources": list(dict.fromkeys(str(item.get("source_name", "")) for item in retrieved)),
        "category": str(case["category"]),
        "severity": str(case.get("severity", "medium")),
        "tags": list(case.get("tags") or []),
        "should_escalate": int(bool(case.get("should_escalate"))),
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "model_name": model_name,
        "target_type": target_type,
        "target_version": target_version,
        "execution_status": status.value,
    }
