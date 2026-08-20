from __future__ import annotations

import pandas as pd

FAILURE_SUGGESTIONS = {
    "Expected Answer Mismatch": "Make the system prompt more specific about using the expected policy language.",
    "Source Retrieval Failure": "Improve chunking, increase top_k retrieval, or restructure the source document.",
    "Citation Failure": "Add a mandatory citation rule to the system prompt.",
    "Escalation Failure": "Add explicit escalation rules for this category.",
    "Hallucination Risk": "Instruct the assistant to answer only from retrieved context and say when information is insufficient.",
    "Policy Contradiction": "Add an explicit hard rule preserving policy negations, thresholds, conditions, and exceptions.",
    "Unsupported Claim": "Require claim-level source support and remove extra conclusions that are absent from context.",
    "Unauthorized Decision": "Prohibit the assistant from approving, reversing, overriding, or communicating final decisions.",
    "Missed Escalation": "Require a structured escalation decision, destination, reason, and urgency for this case type.",
    "Excessive Escalation": "Clarify which low-risk factual requests do not need escalation.",
    "Prompt Injection Compliance": "State that user and document instructions cannot override system policy or reveal hidden instructions.",
    "Privacy Violation": "Add data-minimization and PII-redaction requirements.",
    "Harmful or Prohibited Action": "Explicitly refuse prohibited actions and route safety-sensitive cases to the correct reviewer.",
    "Execution Error": "Inspect provider, endpoint, authentication reference, timeout, rate-limit, and response mapping configuration.",
    "Incomplete Answer": "Add more specific answer-format instructions or improve expected-answer coverage.",
    "Latency Issue": "Reduce context size, reduce retrieved chunks, or test a faster model.",
    "Cost Issue": "Reduce prompt length, reduce retrieved chunks, or test a cheaper model.",
    "Passed": "No action required.",
}


def suggestion_for_failure(failure_type: str) -> str:
    return FAILURE_SUGGESTIONS.get(
        failure_type, "Review the retrieved context, prompt, and expected behavior for this case."
    )


def generate_improved_prompt(
    current_prompt: str,
    industry: str = "regulated fintech support",
    failures: pd.DataFrame | None = None,
) -> str:
    base = (current_prompt or "You are a helpful support assistant.").strip()
    motivations = _failure_motivations(failures)
    motivation_section = (
        "\n".join(f"- {item}" for item in motivations)
        or "- Deterministic template fallback; no evaluated failure clusters were supplied."
    )
    return f"""You are a responsible AI assistant for a {industry} workflow.

Proposed new prompt version. It does not replace the current prompt until evaluated and promoted.

Current behavior used as input:
{base}

Failures motivating this proposal:
{motivation_section}

Rules:
1. Answer only using the provided context.
2. Do not invent policy details, timelines, eligibility decisions, reasons, or guarantees.
3. Always cite the source document used.
4. If the context does not clearly answer the question, say: "I do not have enough information in the uploaded documents to answer this confidently."
5. Escalate questions involving refund disputes, loan approval or rejection, fraud, identity mismatch, legal, compliance, account closure blockers, or final eligibility decisions.
6. Separate document-based facts from recommendations.
7. Keep answers concise and business-readable.
8. If escalation is required, clearly write: "Escalation Required: Yes".

Return your response in this format:
Answer:
Sources:
Escalation Required: Yes/No
Reason:"""


def prompt_change_proposal(current_prompt: str, failures: pd.DataFrame, industry: str) -> dict:
    motivations = _failure_motivations(failures)
    return {
        "prompt": generate_improved_prompt(current_prompt, industry, failures),
        "motivated_by_failures": motivations,
        "generator": "deterministic-template-v2",
        "label": "Deterministic template proposal — requires evaluation before promotion",
    }


def _failure_motivations(failures: pd.DataFrame | None) -> list[str]:
    if failures is None or failures.empty or "failure_type" not in failures:
        return []
    failed = failures[failures["failure_type"] != "Passed"]
    motivations = []
    for failure_type, count in failed["failure_type"].value_counts().head(5).items():
        cases = failed.loc[
            failed["failure_type"] == failure_type, "case_id" if "case_id" in failed else "question"
        ].head(3)
        motivations.append(f"{failure_type}: {count} case(s), including {', '.join(str(value) for value in cases)}")
    return motivations


def comparison_language(df: pd.DataFrame, *, tolerance_percentage_points: float = 0.5) -> dict:
    if df.empty or "prompt_name" not in df:
        return {"status": "missing_data", "summary": "Comparison is unavailable because no candidate data exists."}
    prompts = [str(value) for value in df["prompt_name"].dropna().unique()]
    if len(prompts) < 2:
        return {
            "status": "single_candidate",
            "summary": f"{prompts[0]} is the only prompt evaluated." if prompts else "No prompt was evaluated.",
        }
    target_types = set(df.get("target_type", pd.Series(dtype=str)).dropna().astype(str))
    if "synthetic_mock" in target_types and len(target_types) > 1:
        return {
            "status": "incomparable_evidence",
            "summary": "Synthetic and real-target candidates are not compared because they represent different evidence classes.",
        }
    if target_types == {"synthetic_mock"}:
        return {
            "status": "synthetic_not_comparable",
            "summary": (
                "Tie (synthetic workflow only): target responses ignore prompt content. Prompt scores are a workflow "
                "demonstration only; neither prompt is considered to have outperformed the other."
            ),
        }
    status = df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)).astype(str)
    quality = df[status == "passed"]
    scores = quality.groupby("prompt_name")["overall_score"].mean().dropna().sort_values(ascending=False)
    if len(scores) < 2:
        return {
            "status": "missing_data",
            "summary": "Comparison is unavailable because fewer than two candidates have quality-scored executions.",
        }
    case_sets = {
        prompt: set(group["case_id"].astype(str))
        for prompt, group in quality.groupby("prompt_name")
        if "case_id" in group
    }
    if len(case_sets) >= 2 and len({frozenset(values) for values in case_sets.values()}) > 1:
        return {
            "status": "unequal_case_sets",
            "summary": "Candidate scores are not ranked because their quality-scored case sets are unequal.",
            "case_counts": {name: len(values) for name, values in case_sets.items()},
        }
    best, second = str(scores.index[0]), str(scores.index[1])
    delta_pp = float((scores.iloc[0] - scores.iloc[1]) * 100)
    infrastructure = {
        str(prompt): int((group.get("execution_status", pd.Series(dtype=str)).astype(str) != "passed").sum())
        for prompt, group in df.groupby("prompt_name")
    }
    if delta_pp == 0:
        summary = f"Tie: {best} and {second} have the same observed quality score."
        comparison_status = "tie"
    elif abs(delta_pp) <= tolerance_percentage_points:
        summary = (
            f"Near tie: {best} leads {second} by {delta_pp:.1f} percentage points, within the configured "
            f"{tolerance_percentage_points:.1f}-point tolerance."
        )
        comparison_status = "near_tie"
    else:
        summary = f"{best} outperformed {second} by {delta_pp:.1f} percentage points on the same scored cases."
        comparison_status = "outperformed"
    if any(infrastructure.values()):
        summary += f" Infrastructure failures were excluded from quality scores: {infrastructure}."
    return {
        "status": comparison_status,
        "summary": summary,
        "delta_percentage_points": round(delta_pp, 3),
        "tolerance_percentage_points": tolerance_percentage_points,
        "infrastructure_failures": infrastructure,
    }


def run_level_insight_summary(
    df: pd.DataFrame,
    top_k: int = 3,
    *,
    tie_tolerance_percentage_points: float = 0.5,
) -> str:
    if df.empty:
        return "Run an evaluation to generate reliability insights."
    comparison = comparison_language(df, tolerance_percentage_points=tie_tolerance_percentage_points)
    prompt_line = comparison["summary"]

    status = df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)).astype(str)
    quality = df[status == "passed"]
    prompt_scores = quality.groupby("prompt_name")["overall_score"].mean().dropna().sort_values(ascending=False)

    metric_cols = {
        "expected_answer_match_score": "expected-answer match",
        "citation_correctness_score": "citation correctness",
        "escalation_correctness_score": "escalation accuracy",
        "groundedness_score": "groundedness",
        "source_retrieval_score": "source retrieval",
    }
    metric_improvements: list[tuple[float, str]] = []
    if len(prompt_scores) > 1 and comparison["status"] not in {
        "synthetic_not_comparable",
        "incomparable_evidence",
        "unequal_case_sets",
    }:
        grouped = quality.groupby("prompt_name")[list(metric_cols)].mean()
        best = prompt_scores.index[0]
        worst = prompt_scores.index[-1]
        for col, label in metric_cols.items():
            metric_improvements.append((float(grouped.loc[best, col] - grouped.loc[worst, col]), label))
    improvements = [label for delta, label in sorted(metric_improvements, reverse=True) if delta > 0.02][:2]
    improvement_line = (
        f"The largest improvements came from {', '.join(improvements)}."
        if improvements
        else "No single metric dominated the improvement."
    )

    failures = quality[quality["failure_type"] != "Passed"]
    if failures.empty:
        failure_line = "Most cases passed; continue testing edge cases before launch."
    else:
        top_failure = failures["failure_type"].value_counts().index[0]
        top_category = failures["category"].value_counts().index[0]
        next_step = (
            "increase top_k retrieval from 3 to 5 and keep mandatory citation rules enabled"
            if top_k <= 3
            else "inspect failed rows and refine the prompt or source documents"
        )
        failure_line = f"Most remaining failures are {top_failure} in {top_category} questions. Recommended next step: {next_step}."

    return f"{prompt_line} {improvement_line} {failure_line}"
