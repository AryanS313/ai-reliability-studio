from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections import Counter
from math import sqrt
from typing import Any


class EmbeddingProvider(ABC):
    name: str
    semantic: bool

    @abstractmethod
    def fit_transform(self, texts: list[str]):
        raise NotImplementedError

    @abstractmethod
    def transform(self, texts: list[str]):
        raise NotImplementedError


class LocalTfidfEmbedder(EmbeddingProvider):
    name = "local-tfidf"
    semantic = False

    def __init__(self) -> None:
        self.vectorizer = None
        self.mode = "token"
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
            self.mode = "tfidf"
        except Exception:
            self.vectorizer = None

    def fit_transform(self, texts: list[str]):
        if self.vectorizer is not None:
            return self.vectorizer.fit_transform(texts)
        return [_counter(text) for text in texts]

    def transform(self, texts: list[str]):
        if self.vectorizer is not None:
            return self.vectorizer.transform(texts)
        return [_counter(text) for text in texts]


class SentenceTransformerEmbedder(EmbeddingProvider):
    semantic = True

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("Install the semantic-retrieval extra to use sentence-transformer embeddings.") from exc
        self.name = model_name
        self.model = SentenceTransformer(model_name)
        self.mode = "dense"

    def fit_transform(self, texts: list[str]):
        return self.model.encode(texts, normalize_embeddings=True)

    def transform(self, texts: list[str]):
        return self.model.encode(texts, normalize_embeddings=True)


class TextEmbedder(EmbeddingProvider):
    """Backward-compatible configurable embedder.

    Local development defaults to TF-IDF. Set `EMBEDDING_MODEL` and install the
    semantic-retrieval extra for real semantic embeddings.
    """

    def __init__(self) -> None:
        model_name = os.getenv("EMBEDDING_MODEL", "").strip()
        if model_name:
            self.provider: EmbeddingProvider = SentenceTransformerEmbedder(model_name)
        else:
            self.provider = LocalTfidfEmbedder()
        self.name = self.provider.name
        self.semantic = self.provider.semantic
        self.mode = getattr(self.provider, "mode", "dense")

    def fit_transform(self, texts: list[str]):
        return self.provider.fit_transform(texts)

    def transform(self, texts: list[str]):
        return self.provider.transform(texts)


def cosine_counter(a: Counter, b: Counter) -> float:
    shared = set(a) & set(b)
    numerator = sum(a[token] * b[token] for token in shared)
    denom_a = sqrt(sum(value * value for value in a.values()))
    denom_b = sqrt(sum(value * value for value in b.values()))
    if denom_a == 0 or denom_b == 0:
        return 0.0
    return numerator / (denom_a * denom_b)


def dense_similarities(matrix: Any, query_vector: Any) -> list[float]:
    try:
        values = matrix @ query_vector.T
        if hasattr(values, "toarray"):
            values = values.toarray()
        if hasattr(values, "ravel"):
            return [float(value) for value in values.ravel()]
    except (TypeError, ValueError, AttributeError):
        pass
    return [cosine_counter(vector, query_vector[0]) for vector in matrix]


def _counter(text: str) -> Counter:
    tokens = [
        token for token in "".join(char.lower() if char.isalnum() else " " for char in text).split() if len(token) > 2
    ]
    return Counter(tokens)
