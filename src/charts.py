from __future__ import annotations

import json

import pandas as pd
import plotly.express as px

from src.scoring import launch_readiness_verdict
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
    ]
    for col in numeric_cols:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
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
    return {
        "total_questions": int(df["question"].nunique()),
        "overall_score": float(df["overall_score"].mean() * 100),
        "answer_match": float(df["expected_answer_match_score"].mean() * 100),
        "source_retrieval": float(df["source_retrieval_score"].mean() * 100),
        "citation_rate": float(df["citation_correctness_score"].mean() * 100),
        "groundedness": float(df["groundedness_score"].mean() * 100),
        "escalation_accuracy": float(df["escalation_correctness_score"].mean() * 100),
        "high_risk_count": int((df["hallucination_risk"] == "High").sum()),
        "avg_latency": float(df["latency_ms"].mean()),
        "total_cost": float(df["estimated_cost"].sum()),
        "launch_readiness": launch_readiness_verdict(df),
    }


def prompt_comparison_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("prompt_name", as_index=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(grouped, x="prompt_name", y="overall_score", text_auto=".1f", title="Current Prompt vs Improved Prompt")


def model_comparison_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("model_name", as_index=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(grouped, x="model_name", y="overall_score", text_auto=".1f", title="Model Comparison")


def category_score_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby(["category", "prompt_name"], as_index=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(grouped, x="category", y="overall_score", color="prompt_name", barmode="group", title="Category-wise Performance")


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
    return px.bar(grouped, x="prompt_name", y="latency_ms", color="model_name", barmode="group", title="Latency by Prompt and Model")


def cost_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby(["prompt_name", "model_name"], as_index=False)["estimated_cost"].sum()
    return px.bar(grouped, x="prompt_name", y="estimated_cost", color="model_name", barmode="group", title="Cost by Prompt and Model")


def prompt_metric_table(df: pd.DataFrame) -> pd.DataFrame:
    df = prepare_results(df)
    if df.empty:
        return pd.DataFrame()
    grouped = df.groupby("prompt_name", as_index=False).agg(
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
    except Exception:
        pass
    return str(value or "")

