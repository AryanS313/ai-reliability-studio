from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd

from src import database
from src.llm_client import generate_answer
from src.retrieval import retrieve_chunks
from src.scoring import score_result
from src.suggestions import suggestion_for_failure
from src.utils import format_context
from src.vector_store import SimpleVectorStore


REQUIRED_COLUMNS = {"question", "expected_answer", "expected_source", "category", "should_escalate"}


def validate_eval_dataset(df: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Evaluation dataset is missing columns: {', '.join(sorted(missing))}")


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def normalize_eval_dataset(df: pd.DataFrame) -> pd.DataFrame:
    validate_eval_dataset(df)
    out = df.copy()
    out["should_escalate"] = out["should_escalate"].apply(parse_bool)
    return out


def run_evaluation(
    eval_df: pd.DataFrame,
    chunks: list[dict],
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
) -> pd.DataFrame:
    eval_df = normalize_eval_dataset(eval_df)
    models = model_name if isinstance(model_name, list) else [model_name]
    vector_store = SimpleVectorStore()
    vector_store.build(chunks)
    run_name = f"Reliability Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    all_results: list[dict] = []
    total_steps = len(eval_df) * len(prompts) * len(models)
    completed = 0

    for selected_model in models:
        run_id = database.create_eval_run(
            run_name=run_name,
            model_name=selected_model,
            mode=mode,
            total_questions=len(eval_df),
            project_id=project_id,
            notes=f"top_k={top_k}; similarity_threshold={similarity_threshold}",
        )
        for prompt_name, system_prompt in prompts.items():
            for _, row in eval_df.iterrows():
                question = str(row["question"])
                retrieved = retrieve_chunks(vector_store, question, top_k, similarity_threshold)
                context = format_context(retrieved)
                llm = generate_answer(question, context, system_prompt, selected_model, api_key=api_key)
                scores = score_result(
                    actual_answer=llm["answer"],
                    expected_answer=str(row["expected_answer"]),
                    expected_source=str(row["expected_source"]),
                    should_escalate=bool(row["should_escalate"]),
                    retrieved_chunks=retrieved,
                    latency_ms=llm["latency_ms"],
                    estimated_cost=llm["estimated_cost"],
                    latency_threshold_ms=latency_threshold_ms,
                    cost_threshold_usd=cost_threshold_usd,
                )
                result = {
                    "question": question,
                    "expected_answer": str(row["expected_answer"]),
                    "actual_answer": llm["answer"],
                    "expected_source": str(row["expected_source"]),
                    "retrieved_chunks": retrieved,
                    "category": str(row["category"]),
                    "should_escalate": int(bool(row["should_escalate"])),
                    "latency_ms": llm["latency_ms"],
                    "estimated_cost": llm["estimated_cost"],
                    "prompt_name": prompt_name,
                    "prompt_version": prompt_name,
                    "model_name": llm.get("model", selected_model),
                    "final_prompt": llm.get("final_prompt", ""),
                    **scores,
                }
                result["suggested_fix"] = suggestion_for_failure(result["failure_type"])
                database.save_eval_result(run_id, result)
                all_results.append(result)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total_steps)
    return pd.DataFrame(all_results)


def run_single_test(
    question: str,
    expected_answer: str,
    expected_source: str,
    should_escalate: bool,
    chunks: list[dict],
    prompts: dict[str, str],
    model_name: str,
    top_k: int,
    similarity_threshold: float,
    latency_threshold_ms: float = 3500,
    cost_threshold_usd: float = 0.03,
    api_key: str | None = None,
) -> pd.DataFrame:
    vector_store = SimpleVectorStore()
    vector_store.build(chunks)
    rows = []
    for prompt_name, system_prompt in prompts.items():
        retrieved = retrieve_chunks(vector_store, question, top_k, similarity_threshold)
        context = format_context(retrieved)
        llm = generate_answer(question, context, system_prompt, model_name, api_key=api_key)
        scores = score_result(
            actual_answer=llm["answer"],
            expected_answer=expected_answer,
            expected_source=expected_source,
            should_escalate=should_escalate,
            retrieved_chunks=retrieved,
            latency_ms=llm["latency_ms"],
            estimated_cost=llm["estimated_cost"],
            latency_threshold_ms=latency_threshold_ms,
            cost_threshold_usd=cost_threshold_usd,
        )
        failure = scores["failure_type"]
        rows.append(
            {
                "prompt_name": prompt_name,
                "prompt_version": prompt_name,
                "model_name": llm.get("model", model_name),
                "question": question,
                "actual_answer": llm["answer"],
                "retrieved_chunks": retrieved,
                "retrieved_sources": scores["retrieved_sources"],
                "latency_ms": llm["latency_ms"],
                "estimated_cost": llm["estimated_cost"],
                "final_prompt": llm.get("final_prompt", ""),
                "suggested_fix": suggestion_for_failure(failure),
                **scores,
            }
        )
    return pd.DataFrame(rows)
