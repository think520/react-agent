"""Memory search: FTS5 with progressive relaxation.

Phase 1 uses the raw FTS5 MATCH query (implicit AND). When that yields
nothing — common for multi-word or Chinese queries under the unicode61
tokenizer — phase 2 retries with OR semantics, and phase 3 falls back to
per-token LIKE scanning. The retired JSON vector index is no longer used.
"""

import logging
import re

from .store import MemoryIndexStore

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w一-鿿]+")


def _format(results: list[dict], method: str) -> list[dict]:
    return [
        {
            "text": r["text"],
            "source": r["source"],
            "path": r["path"],
            "date": r["date"],
            "score": abs(r["rank"]) if r.get("rank") else 0,
            "method": method,
        }
        for r in results
    ]


class MemorySearcher:
    """Search across daily and permanent memories using FTS5."""

    def __init__(self, workspace: str, base_dir: str = ".bobodan"):
        self.workspace = workspace
        self.base_dir = base_dir
        self.store = MemoryIndexStore(workspace, base_dir)

    def _search(self, query: str, limit: int, source_filter: str | None) -> list[dict]:
        # Phase 1: raw MATCH (implicit AND)
        results = self.store.search_fts(query, limit=limit, source_filter=source_filter)
        if results:
            return _format(results, "fts5")

        # Phase 2: OR-relaxed MATCH for multi-token queries
        tokens = _TOKEN_RE.findall(query)
        if len(tokens) > 1:
            or_query = " OR ".join(f'"{t}"' for t in tokens)
            results = self.store.search_fts(or_query, limit=limit, source_filter=source_filter)
            if results:
                return _format(results, "fts5_or")

        # Phase 3: per-token LIKE scan (works for CJK substrings)
        for token in tokens or [query]:
            results = self.store._search_like(token, limit=limit, source_filter=source_filter)
            if results:
                return _format(results, "like")
        return []

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search all memories. Returns list of {text, source, path, date, score, method}."""
        return self._search(query, limit, source_filter=None)

    def search_daily(self, query: str, limit: int = 5) -> list[dict]:
        """Search only daily memories."""
        return self._search(query, limit, source_filter="daily")

    def search_permanent(self, query: str, limit: int = 5) -> list[dict]:
        """Search only permanent memories."""
        return self._search(query, limit, source_filter="permanent")
