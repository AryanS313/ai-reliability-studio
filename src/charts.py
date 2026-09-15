from __future__ import annotations

import json
import re

import pandas as pd
import plotly.express as px

from src.aggregation import evaluate_candidates
from src.provenance import evidence_frame
from src.suggestions import run_level_insight_summary

CHART_LABELS = {
    "prompt_name": "Instructions",
    "model_name": "Reported model",
    "category": "Topic",
    "overall_score": "Automated quality score (out of 100)",
    "failure_type": "Finding",
    "hallucination_risk": "Unsupported-answer risk",
    "latency_ms": "Time to answer (milliseconds)",
    "estimated_cost": "Known cost subtotal (USD)",
    "size": "Checks",
}


def prepare_results(df: pd.DataFrame) -> pd.DataFrame:
    df = evidence_frame(df)
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
        "total_cost": float(df["estimated_cost"].sum())
        if "estimated_cost" in df and df["estimated_cost"].notna().all()
        else float("nan"),
        "launch_readiness": next(iter(verdicts.values()))
        if len(verdicts) == 1
        else "Candidate-specific verdicts below",
        "candidate_verdicts": verdicts,
    }


def prompt_comparison_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("prompt_name", as_index=False, dropna=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(
        _display_groups(grouped),
        x="prompt_name",
        y="overall_score",
        text_auto=".1f",
        title="Compare current and candidate instructions",
        labels=CHART_LABELS,
    )


def model_comparison_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("model_name", as_index=False, dropna=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(
        _display_groups(grouped),
        x="model_name",
        y="overall_score",
        text_auto=".1f",
        title="Compare reported models",
        labels=CHART_LABELS,
    )


def category_score_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby(["category", "prompt_name"], as_index=False, dropna=False)["overall_score"].mean()
    grouped["overall_score"] *= 100
    return px.bar(
        _display_groups(grouped),
        x="category",
        y="overall_score",
        color="prompt_name",
        barmode="group",
        title="Answer quality by topic",
        labels=CHART_LABELS,
    )


def failure_distribution_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("failure_type", as_index=False, dropna=False).size()
    return px.pie(
        _display_groups(grouped),
        names="failure_type",
        values="size",
        title="Findings across all checks",
        labels=CHART_LABELS,
    )


def hallucination_distribution_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby("hallucination_risk", as_index=False, dropna=False).size()
    return px.bar(
        _display_groups(grouped),
        x="hallucination_risk",
        y="size",
        text_auto=True,
        title="Unsupported-answer risk",
        labels=CHART_LABELS,
    )


def latency_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby(["prompt_name", "model_name"], as_index=False, dropna=False)["latency_ms"].mean()
    return px.bar(
        _display_groups(grouped),
        x="prompt_name",
        y="latency_ms",
        color="model_name",
        barmode="group",
        title="Time to answer by instructions and reported model",
        labels=CHART_LABELS,
    )


def cost_chart(df: pd.DataFrame):
    df = prepare_results(df)
    grouped = df.groupby(["prompt_name", "model_name"], as_index=False, dropna=False)["estimated_cost"].sum(min_count=1)
    figure = px.bar(
        _display_groups(grouped),
        x="prompt_name",
        y="estimated_cost",
        color="model_name",
        barmode="group",
        title="Known cost observations by instructions and reported model",
        labels=CHART_LABELS,
    )
    missing = int(df["estimated_cost"].isna().sum())
    if missing:
        figure.add_annotation(
            text=f"Cost not reported for {missing} of {len(df)} checks. Shown amounts are incomplete subtotals.",
            xref="paper",
            yref="paper",
            x=0,
            y=1.15,
            showarrow=False,
            xanchor="left",
        )
    return figure


def prompt_metric_table(df: pd.DataFrame) -> pd.DataFrame:
    df = prepare_results(df)
    if df.empty:
        return pd.DataFrame()
    quality = df[df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)).astype(str) == "passed"]
    grouped = quality.groupby(
        [column for column in ["prompt_name", "model_name", "target_type"] if column in quality],
        as_index=False,
        dropna=False,
    ).agg(
        overall_score=("overall_score", "mean"),
        answer_match=("expected_answer_match_score", "mean"),
        source_retrieval=("source_retrieval_score", "mean"),
        citation_correctness=("citation_correctness_score", "mean"),
        groundedness=("groundedness_score", "mean"),
        escalation_accuracy=("escalation_correctness_score", "mean"),
        high_hallucination_risk=("hallucination_risk", lambda s: (s == "High").mean()),
        latency_ms=("latency_ms", "mean"),
        estimated_cost=("estimated_cost", lambda values: values.sum(min_count=1)),
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
    verdicts = []
    for _, row in grouped.iterrows():
        selected = pd.Series(True, index=df.index)
        for column in ["prompt_name", "model_name", "target_type"]:
            if column in grouped:
                selected &= df[column].isna() if pd.isna(row[column]) else df[column].eq(row[column])
        candidates = evaluate_candidates(df[selected])
        verdicts.append(
            next(iter(candidates.values()))["verdict"]
            if len(candidates) == 1
            else "Multiple saved revisions; inspect each release check"
        )
    grouped["verdict"] = verdicts
    return grouped


def insight_summary(df: pd.DataFrame, top_k: int = 3) -> str:
    return run_level_insight_summary(prepare_results(df), top_k=top_k)


def _display_groups(frame: pd.DataFrame) -> pd.DataFrame:
    """Format grouped chart values without changing evidence or merging groups."""
    out = frame.copy()
    for column in ["prompt_name", "model_name", "category", "failure_type", "hallucination_risk"]:
        if column not in out:
            continue
        displayed: dict[str, str] = {}
        used: set[str] = set()
        for value in out[column]:
            key = "" if pd.isna(value) else str(value)
            if key in displayed:
                continue
            label = _chart_value_label(key, column)
            candidate = label
            suffix = 2
            while candidate in used:
                candidate = f"{label} ({suffix})"
                suffix += 1
            displayed[key] = candidate
            used.add(candidate)
        out[column] = out[column].map(lambda value, labels=displayed: labels["" if pd.isna(value) else str(value)])
    return out


def _chart_value_label(value: str, column: str) -> str:
    if not value:
        return "Model not reported" if column == "model_name" else "Not recorded"
    if re.fullmatch(r"(?:v|sha256:)?[0-9a-fA-F]{8,64}", value):
        return "Saved instructions" if column == "prompt_name" else "Saved record"
    if column == "prompt_name":
        return {
            "Current Prompt": "Current instructions",
            "Improved Prompt": "Candidate instructions",
            "Candidate Prompt": "Candidate instructions",
        }.get(value, value)
    if column == "model_name":
        return {"mock-model": "Fictional sample", "external-assistant": "Model not reported"}.get(value, value)
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value).replace("_", " ").replace("-", " ")
    return {
        "passed": "No answer issue flagged",
        "execution error": "Connection or provider problem",
        "needs review": "Needs human review",
        "expected answer mismatch": "Answer differs from the reference",
        "source retrieval failure": "Relevant sources not found",
        "citation failure": "Citation needs review",
        "unsupported claim": "Claim lacks source support",
        "privacy violation": "Private information disclosed",
    }.get(words.lower(), words[:1].upper() + words[1:])


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
