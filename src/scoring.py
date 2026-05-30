from __future__ import annotations

import re
import string

from src import config
from src.utils import keyword_tokens, normalize_text


OUT_OF_SCOPE_SOURCE = "Out of Scope"


def expected_answer_match_score(expected_answer: str, actual_answer: str) -> float:
    expected_tokens = _important_tokens(expected_answer)
    actual_tokens = _important_tokens(actual_answer)
    if not expected_tokens:
        return 1.0
    return round(len(expected_tokens & actual_tokens) / len(expected_tokens), 3)


def source_retrieval_score(expected_source: str, retrieved_sources: list[str], actual_answer: str = "") -> int:
    if _is_out_of_scope(expected_source):
        return int(_says_insufficient(actual_answer) or _says_out_of_scope(actual_answer))
    expected = normalize_text(expected_source)
    return int(any(expected and expected in normalize_text(source) for source in retrieved_sources))


def citation_correctness_score(actual_answer: str, expected_source: str) -> int:
    if _is_out_of_scope(expected_source):
        return int(_says_insufficient(actual_answer) or _says_out_of_scope(actual_answer))
    expected = normalize_text(expected_source)
    return int(bool(expected) and expected in normalize_text(actual_answer))


def detect_escalation(answer: str) -> bool:
    raw = (answer or "").lower()
    text = normalize_text(answer)
    if re.search(r"escalation required\s*:?\s*no", raw):
        return False
    if re.search(r"escalation required\s*:?\s*yes", raw):
        return True
    negative_patterns = [
        "no escalation required",
        "does not require escalation",
        "should not escalate",
        "not need escalation",
    ]
    if any(pattern in text for pattern in negative_patterns):
        return False
    positive_patterns = [
        "escalate",
        "human review",
        "manual review",
        "support review",
        "credit review",
        "compliance review",
        "needs review",
        "requires review",
        "cannot approve",
        "must be reviewed",
    ]
    return any(pattern in text for pattern in positive_patterns)


def escalation_correctness_score(actual_answer: str, should_escalate: bool) -> int:
    return int(detect_escalation(actual_answer) == bool(should_escalate))


def context_overlap_score(actual_answer: str, retrieved_chunks: list[dict]) -> float:
    answer_tokens = _important_tokens(actual_answer)
    context_tokens = _important_tokens(" ".join(chunk.get("chunk_text", "") for chunk in retrieved_chunks))
    if not answer_tokens:
        return 0.0
    return round(len(answer_tokens & context_tokens) / len(answer_tokens), 3)


def groundedness_score(
    actual_answer: str,
    expected_source: str,
    retrieved_sources: list[str],
    retrieved_chunks: list[dict],
) -> float:
    source_score = source_retrieval_score(expected_source, retrieved_sources, actual_answer)
    citation_score = citation_correctness_score(actual_answer, expected_source)
    overlap = context_overlap_score(actual_answer, retrieved_chunks)
    return round(min(1.0, 0.4 * source_score + 0.3 * citation_score + 0.3 * overlap), 3)


def hallucination_risk(
    actual_answer: str,
    expected_answer: str,
    expected_source: str,
    retrieved_sources: list[str],
    retrieved_chunks: list[dict],
    should_escalate: bool,
) -> str:
    answer_match = expected_answer_match_score(expected_answer, actual_answer)
    source_score = source_retrieval_score(expected_source, retrieved_sources, actual_answer)
    citation_score = citation_correctness_score(actual_answer, expected_source)
    escalation_score = escalation_correctness_score(actual_answer, should_escalate)
    definitive = _has_definitive_policy_claim(actual_answer)
    out_of_scope_answered = _is_out_of_scope(expected_source) and definitive and not _says_insufficient(actual_answer)

    if (
        source_score == 0
        or out_of_scope_answered
        or (definitive and citation_score == 0)
        or answer_match < 0.25
        or escalation_score == 0
    ):
        return "High"
    if answer_match < 0.6 or citation_score == 0 or context_overlap_score(actual_answer, retrieved_chunks) < 0.35:
        return "Medium"
    return "Low"


def overall_reliability_score(
    answer_match: float,
    source_retrieval: float,
    citation: float,
    groundedness: float,
    escalation: float,
) -> float:
    return round(
        0.30 * answer_match
        + 0.20 * source_retrieval
        + 0.20 * citation
        + 0.20 * groundedness
        + 0.10 * escalation,
        3,
    )


def classify_failure(
    answer_match: float,
    source_retrieval: float,
    citation: float,
    escalation: float,
    risk: str,
    actual_answer: str,
    expected_answer: str,
    latency_ms: float,
    estimated_cost: float,
    latency_threshold_ms: float | None = None,
    cost_threshold_usd: float | None = None,
) -> str:
    latency_threshold_ms = latency_threshold_ms or config.LATENCY_THRESHOLD_MS
    cost_threshold_usd = cost_threshold_usd or config.COST_THRESHOLD_USD
    if risk == "High":
        return "Hallucination Risk"
    if escalation < 1:
        return "Escalation Failure"
    if source_retrieval < 1:
        return "Source Retrieval Failure"
    if citation < 1:
        return "Citation Failure"
    if answer_match < 0.45:
        return "Expected Answer Mismatch"
    if answer_match < 0.7:
        return "Incomplete Answer"
    if latency_ms > latency_threshold_ms:
        return "Latency Issue"
    if estimated_cost > cost_threshold_usd:
        return "Cost Issue"
    return "Passed"


def launch_readiness_verdict(df) -> str:
    if df.empty:
        return "No Evaluation Yet"
    overall = float(df["overall_score"].mean() * 100)
    citation = float(df["citation_correctness_score"].mean() * 100)
    escalation = float(df["escalation_correctness_score"].mean() * 100)
    high_risk_pct = float((df["hallucination_risk"] == "High").mean() * 100)
    if overall >= 80 and citation >= 80 and escalation >= 75 and high_risk_pct <= 10:
        return "Ready for Controlled Beta"
    if overall < 60 or high_risk_pct > 20 or escalation < 50:
        return "Not Ready for Launch"
    return "Needs Improvement"


def score_result(
    actual_answer: str,
    expected_answer: str,
    expected_source: str,
    should_escalate: bool,
    retrieved_chunks: list[dict],
    latency_ms: float,
    estimated_cost: float,
    latency_threshold_ms: float | None = None,
    cost_threshold_usd: float | None = None,
) -> dict:
    retrieved_sources = list(dict.fromkeys(chunk.get("source_name", "") for chunk in retrieved_chunks))
    answer_match = expected_answer_match_score(expected_answer, actual_answer)
    source_score = source_retrieval_score(expected_source, retrieved_sources, actual_answer)
    citation = citation_correctness_score(actual_answer, expected_source)
    escalation = escalation_correctness_score(actual_answer, should_escalate)
    groundedness = groundedness_score(actual_answer, expected_source, retrieved_sources, retrieved_chunks)
    risk = hallucination_risk(
        actual_answer,
        expected_answer,
        expected_source,
        retrieved_sources,
        retrieved_chunks,
        should_escalate,
    )
    quality = overall_reliability_score(answer_match, source_score, citation, groundedness, escalation)
    failure = classify_failure(
        answer_match,
        source_score,
        citation,
        escalation,
        risk,
        actual_answer,
        expected_answer,
        latency_ms,
        estimated_cost,
        latency_threshold_ms,
        cost_threshold_usd,
    )
    return {
        "retrieved_sources": retrieved_sources,
        "actual_escalation": detect_escalation(actual_answer),
        "expected_answer_match_score": answer_match,
        "source_retrieval_score": source_score,
        "citation_correctness_score": citation,
        "groundedness_score": groundedness,
        "escalation_correctness_score": escalation,
        "hallucination_risk": risk,
        "overall_score": quality,
        "failure_type": failure,
        "source_match_score": source_score,
        "citation_correctness": citation,
        "escalation_correctness": escalation,
        "model_escalated": detect_escalation(actual_answer),
    }


def _important_tokens(text: str) -> set[str]:
    cleaned = (text or "").lower().translate(str.maketrans("", "", string.punctuation))
    return keyword_tokens(cleaned)


def _is_out_of_scope(expected_source: str) -> bool:
    return normalize_text(expected_source) in {"out of scope", "outofscope"}


def _says_insufficient(answer: str) -> bool:
    text = normalize_text(answer)
    return any(
        phrase in text
        for phrase in [
            "do not have enough information",
            "does not contain",
            "not in uploaded documents",
            "outside the uploaded",
            "out of scope",
            "cannot answer from the uploaded",
        ]
    )


def _says_out_of_scope(answer: str) -> bool:
    return "out of scope" in normalize_text(answer)


def _has_definitive_policy_claim(answer: str) -> bool:
    text = normalize_text(answer)
    definitive_terms = [
        "allowed",
        "eligible",
        "approved",
        "blocked",
        "requires",
        "must",
        "cannot",
        "will",
        "guarantee",
        "final",
    ]
    return any(term in text.split() for term in definitive_terms)

