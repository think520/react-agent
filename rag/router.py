"""VectorStoreRouter — thin routing layer over sparse and dense vector stores."""

import logging
import os
from dataclasses import asdict

from .chunker import TextChunk
from .dense_store import DenseVectorStore
from .embeddings import LocalEmbeddingProvider
from .ollama import OllamaEmbeddingClient
from .vector_store import LocalVectorStore
from knowledge.paths import knowledge_dir

logger = logging.getLogger(__name__)

VALID_BACKENDS = {"auto", "local", "ollama"}


class VectorStoreRouter:
    """Routes search/write operations to sparse or dense vector stores.

    Modes:
      - auto: probe Ollama, use dense if available, always dual-write
      - ollama: force dense, fail if unavailable
      - local: force sparse
    """

    def __init__(self, workspace: str, config: dict | None = None):
        rag_config = (config or {}).get("rag") or {}
        self.backend = rag_config.get("embedding_backend", "auto")
        if self.backend not in VALID_BACKENDS:
            logger.warning("Unknown embedding_backend %r, falling back to auto", self.backend)
            self.backend = "auto"

        ollama_url = rag_config.get("ollama_url", "http://localhost:11434")
        ollama_model = rag_config.get("ollama_model", "qwen3-embedding:0.6b")
        probe_timeout = rag_config.get("probe_timeout", 3)
        request_timeout = rag_config.get("request_timeout", 10)

        storage_dir = knowledge_dir(workspace)
        sparse_path = os.path.join(storage_dir, "rag_index.json")
        dense_path = os.path.join(storage_dir, "rag_index_dense.json")

        self.sparse_store = LocalVectorStore(sparse_path)
        self.ollama_client = OllamaEmbeddingClient(
            base_url=ollama_url,
            model=ollama_model,
            probe_timeout=probe_timeout,
            request_timeout=request_timeout,
        )
        self.dense_store = DenseVectorStore(dense_path, self.ollama_client)

        # Determine active backend
        self._active = "sparse"
        self._fallback = None
        self._init_backend()

    def _init_backend(self) -> None:
        if self.backend == "local":
            self._active = "sparse"
            self._fallback = None
            logger.info("[rag] embedding backend: local (sparse)")
            return

        if self.backend == "ollama":
            if self.ollama_client.is_available():
                self._active = "dense"
                self._fallback = None
                info = self.ollama_client.get_model_info()
                logger.info(
                    "[rag] embedding backend: ollama (%s, dim=%s)",
                    info.get("model"),
                    info.get("dim"),
                )
            else:
                logger.error("[rag] Ollama requested but unavailable")
                raise RuntimeError(
                    f"Ollama embedding unavailable at {self.ollama_client.base_url} "
                    f"with model {self.ollama_client.model}"
                )
            return

        # auto mode
        if self.ollama_client.is_available():
            self._active = "dense"
            self._fallback = "sparse"
            info = self.ollama_client.get_model_info()
            logger.info(
                "[rag] embedding backend: ollama (%s, dim=%s), sparse as fallback",
                info.get("model"),
                info.get("dim"),
            )
        else:
            self._active = "sparse"
            self._fallback = None
            logger.info("[rag] embedding backend: local (sparse, Ollama unavailable)")

    def _get_active_store(self):
        if self._active == "dense":
            return self.dense_store
        return self.sparse_store

    def _get_fallback_store(self):
        if self._fallback == "sparse":
            return self.sparse_store
        if self._fallback == "dense":
            return self.dense_store
        return None

    def search(self, query: str, top_k: int = 5, course: str | None = None) -> list[dict]:
        """Search using the active store, with automatic fallback."""
        store = self._get_active_store()
        try:
            results = store.search(query=query, top_k=top_k, course=course)
            if results:
                return results
        except Exception as e:
            logger.warning("[rag] active store search failed: %s", e)

        # Try fallback
        fallback = self._get_fallback_store()
        if fallback is not None:
            logger.info("[rag] falling back to %s store", self._fallback)
            try:
                return fallback.search(query=query, top_k=top_k, course=course)
            except Exception as e:
                logger.warning("[rag] fallback store search also failed: %s", e)

        return []

    def replace(self, chunks: list[TextChunk]) -> None:
        """Replace all chunks. Auto mode dual-writes (chunk once, embed separately)."""
        if self.backend == "local":
            self.sparse_store.replace(chunks)
            return

        if self.backend == "ollama":
            self.dense_store.replace(chunks)
            return

        # auto: dual write
        # Always write sparse (fast, no external dependency)
        self.sparse_store.replace(chunks)
        # Write dense if Ollama is available
        if self.ollama_client.is_available():
            try:
                self.dense_store.replace(chunks)
            except Exception as e:
                logger.warning("[rag] dense index write failed: %s (sparse index still ok)", e)

    def upsert(self, chunks: list[TextChunk]) -> None:
        """Upsert chunks. Auto mode dual-writes."""
        if self.backend == "local":
            self.sparse_store.upsert(chunks)
            return

        if self.backend == "ollama":
            self.dense_store.upsert(chunks)
            return

        # auto: dual write
        self.sparse_store.upsert(chunks)
        if self.ollama_client.is_available():
            try:
                self.dense_store.upsert(chunks)
            except Exception as e:
                logger.warning("[rag] dense index upsert failed: %s", e)

    def remove_by_source(self, source_prefix: str) -> int:
        """Remove chunks by source prefix from all active stores."""
        removed = 0
        if self.backend != "ollama":
            removed += self.sparse_store.remove_by_source(source_prefix)
        if self.backend != "local" and self.ollama_client.is_available():
            try:
                removed += self.dense_store.remove_by_source(source_prefix)
            except Exception:
                pass
        return removed

    def get_backend_info(self) -> dict:
        """Return current backend status for display."""
        info = {
            "active": self._active,
            "fallback": self._fallback,
            "mode": self.backend,
        }
        if self._active == "dense" or self._fallback == "dense":
            model_info = self.ollama_client.get_model_info()
            info["model"] = model_info.get("model")
            info["dim"] = model_info.get("dim")
            stats = self.dense_store.get_stats()
            info["dense_chunks"] = stats.get("chunk_count", 0)
            info["dense_updated_at"] = stats.get("updated_at")
        if self._active == "sparse" or self._fallback == "sparse":
            self.sparse_store.load()
            info["sparse_chunks"] = len(self.sparse_store.chunks)
        return info
