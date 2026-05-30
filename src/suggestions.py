from __future__ import annotations

import pandas as pd


FAILURE_SUGGESTIONS = {
    "Expected Answer Mismatch": "Make the system prompt more specific about using the expected policy language.",
    "Source Retrieval Failure": "Improve chunking, increase top_k retrieval, or restructure the source document.",
    "Citation Failure": "Add a mandatory citation rule to the system prompt.",
    "Escalation Failure": "Add explicit escalation rules for this category.",
    "Hallucination Risk": "Instruct the assistant to answer only from retrieved context and say when information is insufficient.",
    "Incomplete Answer": "Add more specific answer-format instructions or improve expected-answer coverage.",
    "Latency Issue": "Reduce context size, reduce retrieved chunks, or test a faster model.",
    "Cost Issue": "Reduce prompt length, reduce retrieved chunks, or test a cheaper model.",
    "Passed": "No action required.",
}


def suggestion_for_failure(failure_type: str) -> str:
    return FAILURE_SUGGESTIONS.get(failure_type, "Review the retrieved context, prompt, and expected behavior for this case.")


def generate_improved_prompt(current_prompt: str, industry: str = "regulated fintech support") -> str:
    base = (current_prompt or "You are a helpful support assistant.").strip()
    return f"""You are a responsible AI assistant for a {industry} workflow.

Start from this current behavior:
{base}

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


def run_level_insight_summary(df: pd.DataFrame, top_k: int = 3) -> str:
    if df.empty:
        return "Run an evaluation to generate reliability insights."

    prompt_scores = df.groupby("prompt_name")["overall_score"].mean().sort_values(ascending=False)
    if len(prompt_scores) > 1:
        best_prompt = prompt_scores.index[0]
        second_prompt = prompt_scores.index[1]
        delta = (prompt_scores.iloc[0] - prompt_scores.iloc[1]) * 100
        prompt_line = f"{best_prompt} outperformed {second_prompt} by {delta:.1f} percentage points."
    else:
        prompt_line = f"{prompt_scores.index[0]} is the only prompt evaluated."

    metric_cols = {
        "expected_answer_match_score": "expected-answer match",
        "citation_correctness_score": "citation correctness",
        "escalation_correctness_score": "escalation accuracy",
        "groundedness_score": "groundedness",
        "source_retrieval_score": "source retrieval",
    }
    improvements = []
    if len(prompt_scores) > 1:
        grouped = df.groupby("prompt_name")[list(metric_cols)].mean()
        best = prompt_scores.index[0]
        worst = prompt_scores.index[-1]
        for col, label in metric_cols.items():
            improvements.append((grouped.loc[best, col] - grouped.loc[worst, col], label))
    improvements = [label for delta, label in sorted(improvements, reverse=True) if delta > 0.02][:2]
    improvement_line = f"The largest improvements came from {', '.join(improvements)}." if improvements else "No single metric dominated the improvement."

    failures = df[df["failure_type"] != "Passed"]
    if failures.empty:
        failure_line = "Most cases passed; continue testing edge cases before launch."
    else:
        top_failure = failures["failure_type"].value_counts().index[0]
        top_category = failures["category"].value_counts().index[0]
        next_step = "increase top_k retrieval from 3 to 5 and keep mandatory citation rules enabled" if top_k <= 3 else "inspect failed rows and refine the prompt or source documents"
        failure_line = f"Most remaining failures are {top_failure} in {top_category} questions. Recommended next step: {next_step}."

    return f"{prompt_line} {improvement_line} {failure_line}"

