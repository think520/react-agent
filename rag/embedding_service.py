"""EmbeddingService — provider-agnostic facade (rag_design B2).

Keeps the old surface (`is_available` / `embed_texts` / `embed_query` /
`get_model_info`) that the Qdrant store, hybrid retriever and sync backfill
rely on, but the provider itself now comes from
`rag.embedding_provider.create_embedding_provider` — Ollama, an
OpenAI-compatible API, or nothing at all.

The degrade path is unchanged and deliberate: with no available provider,
`embed_texts` returns None and retrieval stays FTS5-only instead of pretending.
"""

from __future__ import annotations

import logging

from rag.embedding_provider import create_embedding_provider

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding service backed by whichever provider the config selects."""

    def __init__(self, config: dict | None = None):
        self.provider = create_embedding_provider(config)

    @property
    def name(self) -> str:
        return str(getattr(self.provider, "name", "unknown"))

    def is_available(self) -> bool:
        """True when the configured provider can plausibly serve a request."""
        try:
            return bool(self.provider.is_available())
        except Exception:
            return False

    def embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        """Embed multiple texts. Returns None if unavailable."""
        if not texts:
            return []
        try:
            if not self.provider.is_available():
                return None
            return self.provider.embed(texts)
        except Exception as e:
            # A provider failure must never take down sync or retrieval.
            logger.warning("Embedding failed via %s: %s", self.name, e)
            return None

    def embed_query(self, query: str) -> list[float] | None:
        """Embed a single query. Returns None if unavailable."""
        result = self.embed_texts([query])
        if result and result[0]:
            return result[0]
        return None

    def get_model_info(self) -> dict:
        """Model metadata, including the dimension Qdrant needs."""
        try:
            info = dict(self.provider.get_model_info())
        except Exception as e:
            logger.warning("Embedding provider info failed via %s: %s", self.name, e)
            info = {"name": self.name, "model": "", "dim": None}
        if not info.get("dim"):
            # No dimension means init_collection never runs and vectors are
            # silently never written (the P1-18 trap), so resolve it once.
            resolve = getattr(self.provider, "resolve_dim", None)
            if callable(resolve) and self.is_available():
                try:
                    resolved = resolve()
                    if resolved:
                        info["dim"] = int(resolved)
                except Exception as e:
                    logger.warning("Could not resolve embedding dimension: %s", e)
        return info
