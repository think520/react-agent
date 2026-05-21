"""Hybrid memory search: FTS5 primary, vector fallback.

FTS5 provides fast keyword search over indexed memory chunks.
When FTS5 returns no results, falls back to the existing vector store.
"""

import logging
from datetime import datetime, timezone

from .store import MemoryIndexStore

logger = logging.getLogger(__name__)


class MemorySearcher:
    """Search across daily and permanent memories using FTS5 + vector fallback."""

    def __init__(self, workspace: str, base_dir: str = ".bobodan"):
        self.workspace = workspace
        self.base_dir = base_dir
        self.store = MemoryIndexStore(workspace, base_dir)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search memories using FTS5 as primary, vector as fallback.

        Returns list of {text, source, path, date, score, method}.
        """
        # Phase 1: FTS5 search
        results = self.store.search_fts(query, limit=limit)

        if results:
            # Record recall for promotion scoring
            for r in results:
                self.store.record_recall(r["id"])
            return [
                {
                    "text": r["text"],
                    "source": r["source"],
                    "path": r["path"],
                    "date": r["date"],
                    "score": abs(r["rank"]) if r["rank"] else 0,
                    "method": "fts5",
                }
                for r in results
            ]

        # Phase 2: Vector fallback
        return self._search_vector(query, limit)

    def search_daily(self, query: str, limit: int = 5) -> list[dict]:
        """Search only daily memories."""
        results = self.store.search_fts(query, limit=limit, source_filter="daily")
        return [
            {
                "text": r["text"],
                "source": r["source"],
                "path": r["path"],
                "date": r["date"],
                "score": abs(r["rank"]) if r["rank"] else 0,
                "method": "fts5",
            }
            for r in results
        ]

    def search_permanent(self, query: str, limit: int = 5) -> list[dict]:
        """Search only permanent memories."""
        results = self.store.search_fts(query, limit=limit, source_filter="permanent")
        if results:
            return [
                {
                    "text": r["text"],
                    "source": r["source"],
                    "path": r["path"],
                    "date": r["date"],
                    "score": abs(r["rank"]) if r["rank"] else 0,
                    "method": "fts5",
                }
                for r in results
            ]
        return self._search_vector(query, limit)

    def _search_vector(self, query: str, limit: int) -> list[dict]:
        """Fallback to existing vector store for permanent memories."""
        try:
            import os
            from rag.vector_store import LocalVectorStore

            index_path = os.path.join(self.workspace, self.base_dir, "memory_index.json")
            if not os.path.exists(index_path):
                return []

            store = LocalVectorStore(index_path)
            store.load()
            if not store.chunks:
                return []

            results = store.search(query, top_k=limit)
            return [
                {
                    "text": r.get("text", ""),
                    "source": r.get("source", "").replace("memory://", "permanent://"),
                    "path": r.get("source", ""),
                    "date": None,
                    "score": r.get("score", 0),
                    "method": "vector",
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("Vector memory search fallback failed: %s", e)
            return []
