from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from src.vector_store import SimpleVectorStore


def retrieve_chunks(
    vector_store: SimpleVectorStore,
    question: str,
    top_k: int,
    similarity_threshold: float,
    *,
    metadata_filters: dict[str, Any] | None = None,
    query_rewriter: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    query = query_rewriter(question) if query_rewriter else question
    results = vector_store.retrieve(
        query,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        metadata_filters=metadata_filters,
    )
    for result in results:
        result["original_query"] = question
        result["retrieval_query"] = query
    return results


def retrieval_metrics(
    retrieved_chunks: list[dict[str, Any]],
    *,
    expected_sources: list[str] | None = None,
    expected_passages: list[str] | None = None,
    relevant_chunk_ids: list[str] | None = None,
    k: int | None = None,
) -> dict[str, float | int | None]:
    items = retrieved_chunks[:k] if k else retrieved_chunks
    relevant_ids = set(str(value) for value in (relevant_chunk_ids or []))
    expected_sources_normalized = {str(value).lower() for value in (expected_sources or [])}
    passages = [str(value).lower() for value in (expected_passages or [])]

    relevance: list[int] = []
    for item in items:
        chunk_id = str(item.get("chunk_id", item.get("id", "")))
        source = str(item.get("source_name", "")).lower()
        text = str(item.get("chunk_text", "")).lower()
        relevant = bool(
            (relevant_ids and chunk_id in relevant_ids)
            or (expected_sources_normalized and source in expected_sources_normalized)
            or (passages and any(_passage_match(passage, text) for passage in passages))
        )
        relevance.append(int(relevant))
    relevant_retrieved = sum(relevance)
    known_relevant_count = len(relevant_ids) or len(passages) or len(expected_sources_normalized)
    precision = relevant_retrieved / len(items) if items else 0.0
    recall = min(1.0, relevant_retrieved / known_relevant_count) if known_relevant_count else None
    first_rank = next((index + 1 for index, value in enumerate(relevance) if value), None)
    dcg = sum(value / math.log2(index + 2) for index, value in enumerate(relevance))
    ideal = sorted(relevance, reverse=True)
    idcg = sum(value / math.log2(index + 2) for index, value in enumerate(ideal))
    return {
        "k": len(items),
        "precision_at_k": round(precision, 4),
        "recall_at_k": round(recall, 4) if recall is not None else None,
        "hit_rate": int(bool(relevant_retrieved)),
        "mrr": round(1 / first_rank, 4) if first_rank else 0.0,
        "ndcg": round(dcg / idcg, 4) if idcg else 0.0,
        "expected_passage_retrieved": int(bool(passages) and bool(relevant_retrieved)),
        "irrelevant_context_rate": round(1 - precision, 4) if items else 0.0,
    }


def _passage_match(expected: str, actual: str) -> bool:
    expected_tokens = set(expected.split())
    actual_tokens = set(actual.split())
    return len(expected_tokens & actual_tokens) / max(1, len(expected_tokens)) >= 0.75
