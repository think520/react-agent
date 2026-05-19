import json
import os
from dataclasses import asdict

from .chunker import TextChunk
from .embeddings import LocalEmbeddingProvider, cosine_similarity


INDEX_VERSION = 1


class LocalVectorStore:
    """JSON-backed sparse vector index for small local knowledge bases."""

    def __init__(self, index_path: str):
        self.index_path = index_path
        self.embedding_provider = LocalEmbeddingProvider()
        self.chunks: list[dict] = []

    def load(self) -> None:
        if not os.path.exists(self.index_path):
            self.chunks = []
            return
        with open(self.index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.chunks = data.get("chunks", [])

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(
                {"version": INDEX_VERSION, "chunks": self.chunks},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def replace(self, chunks: list[TextChunk]) -> None:
        self.chunks = []
        for chunk in chunks:
            item = asdict(chunk)
            item["vector"] = self.embedding_provider.embed(chunk.text)
            self.chunks.append(item)
        self.save()

    def upsert(self, chunks: list[TextChunk]) -> None:
        """Add or update chunks without replacing existing data.

        Chunks are matched by id — existing entries with the same id are
        replaced; new ids are appended.
        """
        self.load()
        existing_ids = {c.get("id") for c in self.chunks}
        for chunk in chunks:
            item = asdict(chunk)
            item["vector"] = self.embedding_provider.embed(chunk.text)
            if chunk.id in existing_ids:
                # Replace existing
                self.chunks = [c for c in self.chunks if c.get("id") != chunk.id]
            self.chunks.append(item)
        self.save()

    def remove_by_source(self, source_prefix: str) -> int:
        """Remove all chunks whose source starts with the given prefix.

        Returns the number of chunks removed.
        """
        self.load()
        before = len(self.chunks)
        self.chunks = [
            c for c in self.chunks
            if not c.get("source", "").startswith(source_prefix)
        ]
        removed = before - len(self.chunks)
        if removed:
            self.save()
        return removed

    def search(self, query: str, top_k: int = 5, course: str | None = None) -> list[dict]:
        self.load()
        query_vector = self.embedding_provider.embed(query)
        scored = []
        for item in self.chunks:
            metadata = item.get("metadata") or {}
            if course and metadata.get("course") != course:
                continue
            score = cosine_similarity(query_vector, item.get("vector") or {})
            if score <= 0:
                continue
            scored.append(
                {
                    "text": item.get("text", ""),
                    "source": item.get("source", ""),
                    "score": round(score, 6),
                    "metadata": metadata,
                }
            )

        scored.sort(key=lambda item: (-item["score"], item["source"]))
        return scored[:max(1, min(int(top_k), 20))]
