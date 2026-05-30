from __future__ import annotations

from src.embeddings import TextEmbedder, cosine_counter


class SimpleVectorStore:
    def __init__(self) -> None:
        self.embedder = TextEmbedder()
        self.chunks: list[dict] = []
        self.matrix = None

    def build(self, chunks: list[dict]) -> None:
        self.chunks = chunks
        texts = [chunk["chunk_text"] for chunk in chunks]
        self.matrix = self.embedder.fit_transform(texts) if texts else None

    def retrieve(self, query: str, top_k: int = 3, similarity_threshold: float = 0.0) -> list[dict]:
        if not self.chunks or self.matrix is None:
            return []

        query_vector = self.embedder.transform([query])
        if self.embedder.mode == "tfidf":
            similarities = (self.matrix @ query_vector.T).toarray().ravel()
        else:
            similarities = [cosine_counter(vector, query_vector[0]) for vector in self.matrix]

        ranked = sorted(enumerate(similarities), key=lambda item: item[1], reverse=True)
        results = []
        for index, score in ranked[:top_k]:
            if float(score) < similarity_threshold:
                continue
            item = dict(self.chunks[index])
            item["similarity"] = float(score)
            results.append(item)
        return results

