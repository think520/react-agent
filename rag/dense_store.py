"""JSON-backed dense vector index for Ollama embeddings."""

import json
import math
import os
from dataclasses import asdict
from datetime import datetime, timezone

from .chunker import TextChunk
from .ollama import OllamaEmbeddingClient

INDEX_VERSION = 1


def _cosine_similarity(a: list[float], b: list[float], norm_b: float) -> float:
    """Cosine similarity between query vector a and pre-normalized chunk vector b.

    `norm_b` is the pre-computed L2 norm of b (stored at index time).
    a is normalized on the fly since it's only computed once per query.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _l2_norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


class DenseVectorStore:
    """JSON-backed dense vector index using Ollama embeddings."""

    def __init__(self, index_path: str, embedding_client: OllamaEmbeddingClient):
        self.index_path = index_path
        self.client = embedding_client
        self.chunks: list[dict] = []
        self.meta: dict = {}

    def load(self) -> None:
        if not os.path.exists(self.index_path):
            self.chunks = []
            self.meta = {}
            return
        with open(self.index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.chunks = data.get("chunks", [])
        self.meta = {
            "version": data.get("version"),
            "backend": data.get("backend"),
            "model": data.get("model"),
            "embedding_dim": data.get("embedding_dim"),
            "updated_at": data.get("updated_at"),
        }

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        model_info = self.client.get_model_info()
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": INDEX_VERSION,
                    "backend": "ollama",
                    "model": model_info.get("model", ""),
                    "embedding_dim": model_info.get("dim"),
                    "updated_at": now,
                    "chunks": self.chunks,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def replace(self, chunks: list[TextChunk]) -> None:
        """Full rebuild: embed all chunks and replace the index."""
        if not chunks:
            self.chunks = []
            self.save()
            return
        texts = [c.text for c in chunks]
        vectors = self.client.embed(texts)
        self.chunks = []
        for chunk, vec in zip(chunks, vectors):
            item = asdict(chunk)
            item["vector"] = vec
            item["norm"] = _l2_norm(vec)
            self.chunks.append(item)
        self.save()

    def upsert(self, chunks: list[TextChunk]) -> None:
        """Add or update chunks by id."""
        self.load()
        existing_ids = {c.get("id") for c in self.chunks}
        if not chunks:
            return
        texts = [c.text for c in chunks]
        vectors = self.client.embed(texts)
        for chunk, vec in zip(chunks, vectors):
            item = asdict(chunk)
            item["vector"] = vec
            item["norm"] = _l2_norm(vec)
            if chunk.id in existing_ids:
                self.chunks = [c for c in self.chunks if c.get("id") != chunk.id]
            self.chunks.append(item)
        self.save()

    def remove_by_source(self, source_prefix: str) -> int:
        """Remove chunks whose source starts with the given prefix."""
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
        """Search by cosine similarity against dense vectors."""
        self.load()
        if not self.chunks:
            return []
        try:
            vectors = self.client.embed([query])
        except Exception:
            return []
        if not vectors or not vectors[0]:
            return []
        query_vec = vectors[0]

        scored = []
        for item in self.chunks:
            metadata = item.get("metadata") or {}
            if course and metadata.get("course") != course:
                continue
            vec = item.get("vector") or []
            norm = item.get("norm") or _l2_norm(vec)
            score = _cosine_similarity(query_vec, vec, norm)
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

        scored.sort(key=lambda x: (-x["score"], x["source"]))
        return scored[:max(1, min(int(top_k), 20))]

    def get_stats(self) -> dict:
        """Return index statistics."""
        self.load()
        return {
            "chunk_count": len(self.chunks),
            "model": self.meta.get("model"),
            "dim": self.meta.get("embedding_dim"),
            "updated_at": self.meta.get("updated_at"),
            "backend": self.meta.get("backend"),
        }

    def check_model_match(self) -> bool:
        """Check if stored index model matches current client model.

        Returns True if match, False if model changed (rebuild needed).
        """
        self.load()
        stored_model = self.meta.get("model")
        if not stored_model:
            return True  # no existing index, no conflict
        return stored_model == self.client.model
