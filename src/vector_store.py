from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from src.embeddings import EmbeddingProvider, TextEmbedder, dense_similarities


class HybridRetriever:
    def __init__(
        self,
        embedder: EmbeddingProvider | None = None,
        *,
        semantic_weight: float = 0.65,
        lexical_weight: float = 0.35,
        reranker: Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    ) -> None:
        if semantic_weight < 0 or lexical_weight < 0 or semantic_weight + lexical_weight <= 0:
            raise ValueError("Retrieval weights must be non-negative and have a positive sum")
        total = semantic_weight + lexical_weight
        self.semantic_weight = semantic_weight / total
        self.lexical_weight = lexical_weight / total
        self.embedder = embedder or TextEmbedder()
        self.reranker = reranker
        self.chunks: list[dict[str, Any]] = []
        self.matrix = None
        self.lexical_documents: list[Counter[str]] = []
        self.document_frequency: Counter[str] = Counter()

    def build(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = list(chunks)
        texts = [str(chunk["chunk_text"]) for chunk in chunks]
        self.matrix = self.embedder.fit_transform(texts) if texts else None
        self.lexical_documents = [Counter(_tokens(text)) for text in texts]
        self.document_frequency = Counter(token for document in self.lexical_documents for token in set(document))

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        similarity_threshold: float = 0.05,
        *,
        metadata_filters: dict[str, Any] | None = None,
        candidate_multiplier: int = 4,
    ) -> list[dict[str, Any]]:
        if not self.chunks or self.matrix is None:
            return []
        query_vector = self.embedder.transform([query])
        semantic_scores = dense_similarities(self.matrix, query_vector)
        lexical_scores = self._lexical_scores(query)
        ranked = []
        for index, (semantic, lexical) in enumerate(zip(semantic_scores, lexical_scores, strict=False)):
            chunk = self.chunks[index]
            if metadata_filters and not all(chunk.get(key) == value for key, value in metadata_filters.items()):
                continue
            score = self.semantic_weight * _normalize_score(semantic) + self.lexical_weight * lexical
            item = dict(chunk)
            item.update(
                {
                    "similarity": float(score),
                    "semantic_score": float(semantic),
                    "lexical_score": float(lexical),
                    "embedding_provider": self.embedder.name,
                    "semantic_embeddings": bool(self.embedder.semantic),
                }
            )
            ranked.append(item)
        ranked.sort(key=lambda item: item["similarity"], reverse=True)
        candidates = ranked[: max(top_k, top_k * candidate_multiplier)]
        if self.reranker:
            candidates = self.reranker(query, candidates)
            for rank, item in enumerate(candidates):
                item["rerank_position"] = rank + 1
        return [item for item in candidates if float(item["similarity"]) >= similarity_threshold][:top_k]

    def _lexical_scores(self, query: str) -> list[float]:
        query_tokens = _tokens(query)
        document_count = len(self.lexical_documents)
        scores = []
        for document in self.lexical_documents:
            score = 0.0
            length = max(1, sum(document.values()))
            for token in query_tokens:
                tf = document[token]
                if not tf:
                    continue
                idf = math.log(
                    1 + (document_count - self.document_frequency[token] + 0.5) / (self.document_frequency[token] + 0.5)
                )
                score += idf * ((tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / 150)))
            scores.append(score)
        maximum = max(scores, default=0.0)
        return [score / maximum if maximum else 0.0 for score in scores]


class SimpleVectorStore(HybridRetriever):
    """Backward-compatible name for the lightweight hybrid retriever."""


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[A-Za-z0-9]+", (text or "").lower()) if len(token) > 1]


def _normalize_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
