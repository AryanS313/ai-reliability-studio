from __future__ import annotations

import json

import pandas as pd
import plotly.express as px

from src.aggregation import evaluate_candidates
from src.suggestions import run_level_insight_summary


def prepare_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "prompt_name" not in out and "prompt_version" in out:
        out["prompt_name"] = out["prompt_version"]
    numeric_cols = [
        "overall_score",
        "expected_answer_match_score",
        "source_retrieval_score",
        "citation_correctness_score",
        "groundedness_score",
        "escalation_correctness_score",
        "latency_ms",
        "estimated_cost",
        "citation_completeness",
        "evaluator_confidence",
    ]
    for col in numeric_cols:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "retrieved_sources" in out:
        out["retrieved_sources_display"] = out["retrieved_sources"].apply(_display_json_list)
    else:
        out["retrieved_sources_display"] = ""
    if "actual_escalation" in out:
        out["actual_escalation"] = out["actual_escalation"].astype(bool)
    return out


def metric_summary(df: pd.DataFrame) -> dict:
    df = prepare_results(df)
    if df.empty:
        return {
            "total_questions": 0,
            "total_executions": 0,
            "passed_executions": 0,
            "failed_executions": 0,
            "overall_score": 0,
            "answer_match": 0,
            "source_retrieval": 0,
            "citation_rate": 0,
            "groundedness": 0,
            "escalation_accuracy": 0,
            "high_risk_count": 0,
            "avg_latency": 0,
            "total_cost": 0,
            "launch_readiness": "No Evaluation Yet",
        }
    status = df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)).astype(str)
    quality = df[status == "passed"]
    candidates = evaluate_candidates(df)
    verdicts = {key: value["verdict"] for key, value in candidates.items()}
    return {
        "total_questions": int(df["case_id"].nunique() if "case_id" in df else df["question"].nunique()),
        "total_executions": len(df),
        "passed_executions": int((status == "passed").sum()),
        "failed_executions": int((status != "passed").sum()),
        "overall_score": _mean_percent(quality, "overall_score"),
        "answer_match": _mean_percent(quality, "expected_answer_match_score"),
        "source_retrieval": _mean_percent(quality, "source_retrieval_score"),
        "citation_rate": _mean_percent(quality, "citation_correctness_score"),
        "groundedness": _mean_percent(quality, "groundedness_score"),
        "escalation_accuracy": _mean_percent(quality, "escalation_correctness_score"),
        "high_risk_count": int((quality.get("hallucination_risk", pd.Series(dtype=str)) == "High").sum()),
        "avg_latency": float(quality["latency_ms"].mean()) if not quality.empty and "latency_ms" in quality else 0.0,
        "total_cost": float(quality["estimated_cost"].fillna(0).sum())
        if not quality.empty and "estimated_cost" in quality
        else 0.0,
        "launch_readiness": next(iter(verdicts.values()))
        if len(verdicts) == 1
        else "Candidate-specific verdicts below",
        "candidate_verdicts": verdicts,
    }


def prompt_comparison_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("prompt_name", as_index=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(
        grouped, x="prompt_name", y="overall_score", text_auto=".1f", title="Current Prompt vs Improved Prompt"
    )


def model_comparison_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("model_name", as_index=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(grouped, x="model_name", y="overall_score", text_auto=".1f", title="Model Comparison")


def category_score_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby(["category", "prompt_name"], as_index=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(
        grouped,
        x="category",
        y="overall_score",
        color="prompt_name",
        barmode="group",
        title="Category-wise Performance",
    )


def failure_distribution_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("failure_type", as_index=False).size()
    return px.pie(grouped, names="failure_type", values="size", title="Failure Type Distribution")


def hallucination_distribution_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("hallucination_risk", as_index=False).size()
    return px.bar(grouped, x="hallucination_risk", y="size", text_auto=True, title="Hallucination Risk Distribution")


def latency_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby(["prompt_name", "model_name"], as_index=False)["latency_ms"].mean()
    return px.bar(
        grouped,
        x="prompt_name",
        y="latency_ms",
        color="model_name",
        barmode="group",
        title="Latency by Prompt and Model",
    )


def cost_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby(["prompt_name", "model_name"], as_index=False)["estimated_cost"].sum()
    return px.bar(
        grouped,
        x="prompt_name",
        y="estimated_cost",
        color="model_name",
        barmode="group",
        title="Cost by Prompt and Model",
    )


def prompt_metric_table(df: pd.DataFrame) -> pd.DataFrame:
    df = prepare_results(df)
    if df.empty:
        return pd.DataFrame()
    quality = df[df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)).astype(str) == "passed"]
    grouped = quality.groupby(
        [column for column in ["prompt_name", "model_name", "target_type"] if column in quality], as_index=False
    ).agg(
        overall_score=("overall_score", "mean"),
        answer_match=("expected_answer_match_score", "mean"),
        source_retrieval=("source_retrieval_score", "mean"),
        citation_correctness=("citation_correctness_score", "mean"),
        groundedness=("groundedness_score", "mean"),
        escalation_accuracy=("escalation_correctness_score", "mean"),
        high_hallucination_risk=("hallucination_risk", lambda s: (s == "High").mean()),
        latency_ms=("latency_ms", "mean"),
        estimated_cost=("estimated_cost", "sum"),
    )
    percent_cols = [
        "overall_score",
        "answer_match",
        "source_retrieval",
        "citation_correctness",
        "groundedness",
        "escalation_accuracy",
        "high_hallucination_risk",
    ]
    for col in percent_cols:
        grouped[col] = grouped[col] * 100
    verdicts = evaluate_candidates(df)
    if len(verdicts) == len(grouped):
        grouped["verdict"] = [value["verdict"] for value in verdicts.values()]
    return grouped


def insight_summary(df: pd.DataFrame, top_k: int = 3) -> str:
    return run_level_insight_summary(prepare_results(df), top_k=top_k)


def _display_json_list(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return ", ".join(str(item) for item in parsed)
    except (json.JSONDecodeError, TypeError):
        return str(value or "")
    return str(value or "")


def _mean_percent(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").dropna().mean() * 100)
