from __future__ import annotations

from collections import Counter
from math import sqrt


class TextEmbedder:
    """Small, robust embedder using sklearn TF-IDF when present, token vectors otherwise."""

    def __init__(self) -> None:
        self.vectorizer = None
        self.mode = "token"
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
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


def _counter(text: str) -> Counter:
    tokens = [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(t) > 2]
    return Counter(tokens)


def cosine_counter(a: Counter, b: Counter) -> float:
    shared = set(a) & set(b)
    numerator = sum(a[token] * b[token] for token in shared)
    denom_a = sqrt(sum(value * value for value in a.values()))
    denom_b = sqrt(sum(value * value for value in b.values()))
    if denom_a == 0 or denom_b == 0:
        return 0.0
    return numerator / (denom_a * denom_b)

