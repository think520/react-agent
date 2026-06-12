"""MemoryService — business logic for permanent memory, daily memory, and promotion.

Used by both cli/repl.py and tools/memory_tools.py.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def _err(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


class MemoryService:
    """Stateless service: each method creates its own managers."""

    def __init__(self, workspace: str = "."):
        self.workspace = workspace

    def _manager(self):
        from core.memory import MemoryManager
        return MemoryManager(self.workspace)

    # --- Permanent memory ---

    def save(
        self,
        name: str,
        description: str,
        content: str,
        entry_type: str = "user",
    ) -> dict[str, Any]:
        if not name or not name.strip():
            return _err("name is required")
        if not content or not content.strip():
            return _err("content is required")

        valid_types = {"user", "feedback", "project", "reference"}
        if entry_type not in valid_types:
            entry_type = "user"

        manager = self._manager()
        entry = manager.save(
            name=name.strip(),
            description=description.strip() if description else "",
            content=content.strip(),
            entry_type=entry_type,
        )
        return _ok(name=entry.name, type=entry.type)

    def recall(self, query: str, top_k: int = 5) -> dict[str, Any]:
        if not query or not query.strip():
            return _err("query is required")

        manager = self._manager()
        results = manager.search(query.strip(), top_k=max(1, min(top_k, 10)))

        if not results:
            entries = manager.list_entries()
            if entries:
                all_entries = [
                    {"name": e.name, "type": e.type, "description": e.description}
                    for e in entries
                ]
                return _ok(results=[], fallback=all_entries)
            return _ok(results=[], fallback=[])

        formatted = []
        for r in results:
            source = r.get("source", "").replace("memory://", "").replace("permanent://", "")
            formatted.append({
                "source": source,
                "score": r.get("score", 0),
                "text": r.get("text", "")[:200],
                "method": r.get("metadata", {}).get("method", ""),
            })
        return _ok(results=formatted)

    def list_entries(self) -> dict[str, Any]:
        manager = self._manager()
        entries = manager.list_entries()
        result = [
            {"name": e.name, "type": e.type, "description": e.description}
            for e in entries
        ]
        return _ok(entries=result)

    def get_entry(self, name: str) -> dict[str, Any]:
        manager = self._manager()
        manager.load_entries()
        entry = manager.get_entry(name)
        if not entry:
            return _err(f"Memory not found: {name}")
        return _ok(
            name=entry.name,
            type=entry.type,
            description=entry.description,
            content=entry.content,
            created=entry.created,
            updated=entry.updated,
            file_path=entry.file_path,
        )

    def forget(self, name: str) -> dict[str, Any]:
        manager = self._manager()
        if manager.forget(name):
            return _ok(name=name)
        return _err(f"Memory not found: {name}")

    # --- Daily memory ---

    def daily_save(self, content: str, tags: list[str] | None = None) -> dict[str, Any]:
        if not content or not content.strip():
            return _err("content is required")

        from memory.daily import DailyMemoryManager
        daily = DailyMemoryManager(self.workspace)
        filepath = daily.append(content.strip(), tags=tags)

        # Index in FTS5 (best-effort)
        try:
            from memory.store import MemoryIndexStore
            import datetime as dt
            today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            idx = MemoryIndexStore(self.workspace)
            idx.index_text(path=filepath, source="daily", text=content.strip(), date=today)
        except Exception:
            pass

        return _ok(path=filepath, date=daily._today_str())

    def daily_read(self, date: str | None = None) -> dict[str, Any]:
        from memory.daily import DailyMemoryManager
        daily = DailyMemoryManager(self.workspace)

        if not date:
            content = daily.get_today()
            date_label = daily._today_str()
        else:
            content = daily.read(date)
            date_label = date

        return _ok(content=content, date=date_label)

    # --- Promotion ---

    def promote(self, dry_run: bool = False) -> dict[str, Any]:
        from memory.promotion import PromotionEngine
        engine = PromotionEngine(self.workspace)

        candidates = engine.run_promotion_check()
        if not candidates:
            return _ok(candidates=[], promoted=0, dry_run=dry_run)

        promoted_count = 0
        results = []
        for c in candidates:
            entry = {
                "path": c["path"],
                "date": c["date"],
                "score": c["score"],
                "eligible": c["eligible"],
                "recall_count": c["recall_count"],
                "frequency": c["frequency"],
                "quiz": c["quiz"],
                "recency": c["recency"],
            }
            if c["eligible"] and not dry_run:
                result = engine.promote(c["path"])
                entry["promoted"] = result["promoted"]
                entry["details"] = result.get("details", "")
                if result["promoted"]:
                    promoted_count += 1
            else:
                entry["promoted"] = False
            results.append(entry)

        return _ok(candidates=results, promoted=promoted_count, dry_run=dry_run)

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        manager = self._manager()
        stats = manager.get_stats()
        return _ok(**stats)
