from __future__ import annotations

from src.vector_store import SimpleVectorStore


def retrieve_chunks(
    vector_store: SimpleVectorStore,
    question: str,
    top_k: int,
    similarity_threshold: float,
) -> list[dict]:
    return vector_store.retrieve(question, top_k=top_k, similarity_threshold=similarity_threshold)

