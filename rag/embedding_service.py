"""EmbeddingService — thin wrapper around OllamaEmbeddingClient.

Provides a unified interface for the Qdrant store and HybridRetriever
to get embeddings. Gracefully returns None when Ollama is unavailable.
"""

from __future__ import annotations

import logging

from rag.ollama import OllamaEmbeddingClient

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding service backed by Ollama."""

    def __init__(self, config: dict | None = None):
        rag_cfg = (config or {}).get("rag", {})
        self.client = OllamaEmbeddingClient(
            base_url=rag_cfg.get("ollama_url", "http://localhost:11434"),
            model=rag_cfg.get("ollama_model", "qwen3-embedding:0.6b"),
            probe_timeout=rag_cfg.get("probe_timeout", 3),
            request_timeout=rag_cfg.get("request_timeout", 10),
        )

    def is_available(self) -> bool:
        """Check if Ollama embedding is available."""
        try:
            return self.client.is_available()
        except Exception:
            return False

    def embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        """Embed multiple texts. Returns None if unavailable."""
        if not texts:
            return []
        try:
            if not self.client.is_available():
                return None
            return self.client.embed(texts)
        except Exception as e:
            logger.warning("Embedding failed: %s", e)
            return None

    def embed_query(self, query: str) -> list[float] | None:
        """Embed a single query. Returns None if unavailable."""
        result = self.embed_texts([query])
        if result and result[0]:
            return result[0]
        return None

    def get_model_info(self) -> dict:
        """Return model info."""
        return self.client.get_model_info()
