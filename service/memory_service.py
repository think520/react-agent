"""MemoryService — business logic for permanent memory, daily memory, and promotion.

Used by both cli/repl.py and tools/memory_tools.py.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import re
from typing import Any


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def _err(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


class MemoryService:
    """Stateless service: each method creates its own managers."""

    def __init__(self, workspace: str = ".", home: str | None = None, legacy_workspace: str | None = None):
        self.workspace = workspace
        self.home = home
        self.legacy_workspace = legacy_workspace or workspace

    def _personal_store(self):
        from memory.personal_store import PersonalKnowledgeStore
        return PersonalKnowledgeStore(self.workspace, home=self.home)

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

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        manager = self._manager()
        stats = manager.get_stats()
        return _ok(**stats)

    # --- Structured personal knowledge ---

    def overview(self) -> dict[str, Any]:
        return _ok(**self._personal_store().overview())

    def list_knowledge(self, scope: str = "all", query: str = "", kind: str | None = None,
                       limit: int = 100) -> dict[str, Any]:
        return _ok(items=self._personal_store().list_items(scope=scope, query=query, kind=kind, limit=limit))

    def create_knowledge(self, *, scope: str, kind: str, title: str, content: str,
                         pinned: bool = False, evidence: list[dict] | None = None) -> dict[str, Any]:
        if self.contains_secret(f"{title}\n{content}"):
            return _err("Passwords, API keys, tokens, and other secrets cannot be saved as personal knowledge.")
        try:
            item = self._personal_store().create_item(
                scope=scope, kind=kind, title=title, content=content,
                pinned=pinned, evidence=evidence,
            )
        except ValueError as exc:
            return _err(str(exc))
        return _ok(item=item)

    def get_knowledge(self, item_id: str) -> dict[str, Any]:
        item = self._personal_store().get_item(item_id)
        return _ok(item=item) if item else _err("Personal knowledge item not found")

    def update_knowledge(self, item_id: str, revision: int, patch: dict[str, Any]) -> dict[str, Any]:
        proposed_text = "\n".join(str(patch.get(key) or "") for key in ("title", "content") if key in patch)
        if self.contains_secret(proposed_text):
            return _err("Secrets cannot be saved as personal knowledge.")
        try:
            item = self._personal_store().update_item(item_id, revision, patch)
        except FileNotFoundError as exc:
            return _err(str(exc))
        except RuntimeError:
            return _err("knowledge_revision_conflict")
        except ValueError as exc:
            return _err(str(exc))
        return _ok(item=item)

    def delete_knowledge(self, item_id: str) -> dict[str, Any]:
        if not self._personal_store().delete_item(item_id):
            return _err("Personal knowledge item not found")
        return _ok(deleted=True, item_id=item_id)

    def list_candidates(self, status: str = "pending", scope: str = "all", limit: int = 100) -> dict[str, Any]:
        return _ok(candidates=self._personal_store().list_candidates(status=status, scope=scope, limit=limit))

    def add_candidate(self, **values: Any) -> dict[str, Any]:
        if self.contains_secret(f"{values.get('title') or ''}\n{values.get('content') or ''}"):
            return _err("Secrets cannot be stored as memory candidates.")
        try:
            candidate = self._personal_store().add_candidate(**values)
        except ValueError as exc:
            return _err(str(exc))
        return _ok(candidate=candidate, duplicate=candidate is None)

    def confirm_candidate(self, candidate_id: str, edits: dict[str, Any] | None = None) -> dict[str, Any]:
        edits = edits or {}
        store = self._personal_store()
        candidate = store.get_candidate(candidate_id)
        proposed_title = edits.get("title", candidate.get("title") if candidate else "")
        proposed_content = edits.get("content", candidate.get("content") if candidate else "")
        if self.contains_secret(f"{proposed_title or ''}\n{proposed_content or ''}"):
            return _err("Secrets cannot be saved as personal knowledge.")
        try:
            item, candidate = store.confirm_candidate(candidate_id, edits)
        except (FileNotFoundError, ValueError) as exc:
            return _err(str(exc))
        return _ok(item=item, candidate=candidate)

    def reject_candidate(self, candidate_id: str) -> dict[str, Any]:
        try:
            candidate = self._personal_store().reject_candidate(candidate_id)
        except FileNotFoundError as exc:
            return _err(str(exc))
        return _ok(candidate=candidate)

    def record_event(self, **values: Any) -> dict[str, Any]:
        try:
            event = self._personal_store().record_event(**values)
        except ValueError as exc:
            return _err(str(exc))
        return _ok(event=event)

    def list_events(self, limit: int = 100, event_type: str | None = None) -> dict[str, Any]:
        return _ok(events=self._personal_store().list_events(limit=limit, event_type=event_type))

    def update_reading_progress(self, document_id: str, progress: int, opened: bool = False) -> dict[str, Any]:
        if not document_id.strip():
            return _err("document_id is required")
        return _ok(progress=self._personal_store().update_reading_progress(document_id, progress, opened=opened))

    def export_knowledge(self, scope: str = "all") -> dict[str, Any]:
        return _ok(content=self._personal_store().export_markdown(scope=scope))

    def legacy_preview(self) -> dict[str, Any]:
        from core.memory import MemoryManager
        from pathlib import Path

        manager = MemoryManager(self.legacy_workspace)
        entries = manager.list_entries()
        daily_dir = Path(self.legacy_workspace) / ".bobodan" / "daily"
        daily = sorted(path.name for path in daily_dir.glob("*.md")) if daily_dir.exists() else []
        return _ok(
            entries=[{
                "name": entry.name,
                "type": entry.type,
                "description": entry.description,
                "content_preview": entry.content[:500],
                "suggested_scope": "global" if entry.type in {"user", "feedback"} else "library",
                "suggested_kind": "profile_fact" if entry.type == "user" else "course_insight",
            } for entry in entries],
            daily_files=daily,
        )

    def import_legacy(self, selections: list[dict[str, str]]) -> dict[str, Any]:
        from core.memory import MemoryManager

        manager = MemoryManager(self.legacy_workspace)
        by_name = {entry.name: entry for entry in manager.list_entries()}
        created = []
        skipped = []
        for selection in selections:
            entry = by_name.get(str(selection.get("name") or ""))
            if not entry:
                skipped.append(selection.get("name"))
                continue
            result = self.add_candidate(
                scope=selection.get("scope", "global"),
                kind=selection.get("kind", "profile_fact"),
                operation="create",
                title=entry.name,
                content=entry.content,
                confidence=1.0,
                reason=f"Imported from legacy memory: {entry.description or entry.name}",
                evidence=[{"source_type": "legacy_memory", "source_id": entry.name}],
                generated_by="legacy_import",
            )
            if result.get("candidate"):
                created.append(result["candidate"])
            else:
                skipped.append(entry.name)
        return _ok(created=created, skipped=skipped)

    def personalization_context(self, query: str, max_chars: int = 2000) -> dict[str, Any]:
        store = self._personal_store()
        pinned = [item for item in store.list_items(scope="global", limit=100) if item["pinned"]][:3]
        relevant = store.list_items(query=query, limit=8)
        seen = {item["id"] for item in pinned}
        selected = pinned + [item for item in relevant if item["id"] not in seen][:5]
        lines = []
        refs = []
        used = 0
        for item in selected:
            line = f"- [{item['scope']}/{item['kind']}] {item['title']}: {item['content']}"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
            refs.append({
                "id": item["id"], "title": item["title"], "scope": item["scope"],
                "kind": item["kind"], "content": item["content"],
                "updated_at": item["updated_at"],
            })

        try:
            from learning.store import LearningStore
            mastery = LearningStore(self.workspace).list_mastery(limit=30)
            normalized_query = query.casefold()
            asks_for_status = any(word in normalized_query for word in ("复习", "练习", "薄弱", "掌握", "review", "practice"))
            relevant_mastery = [
                item for item in mastery
                if item.concept.casefold() in normalized_query
                or normalized_query in item.concept.casefold()
                or (asks_for_status and item.status in {"learning", "needs_review"})
            ]
            ranked = sorted(
                relevant_mastery,
                key=lambda item: (
                    0 if item.concept.casefold() in normalized_query else 1,
                    item.score,
                    item.updated_at,
                ),
            )[:5]
            if ranked:
                lines.append("掌握度摘要：")
            for item in ranked:
                line = f"- {item.concept}: {item.status}, {round(item.score * 100)}%"
                if used + len(line) > max_chars:
                    break
                lines.append(line)
                used += len(line)
                refs.append({
                    "id": f"mastery:{item.concept}",
                    "title": item.concept,
                    "scope": "library",
                    "kind": "mastery",
                    "content": f"{item.status}, {round(item.score * 100)}%",
                    "updated_at": item.updated_at,
                })
        except Exception:
            pass
        return _ok(content="\n".join(lines), references=refs)

    @staticmethod
    def contains_secret(content: str) -> bool:
        patterns = [
            r"(?i)api[_ -]?key\s*[:=]", r"(?i)access[_ -]?token\s*[:=]",
            r"(?i)token\s*[:=]", r"(?i)password\s*[:=]", r"(?i)secret\s*[:=]",
            r"\bsk-[A-Za-z0-9_-]{16,}\b", r"\bgh[opsu]_[A-Za-z0-9]{20,}\b",
            r"(?:密码|密钥|令牌)\s*[:：=]",
        ]
        return any(re.search(pattern, content or "") for pattern in patterns)

    @staticmethod
    def is_sensitive(content: str) -> bool:
        words = ("诊断", "疾病", "健康", "残障", "宗教", "政治", "收入", "住址", "身份证", "sexual", "medical")
        lowered = (content or "").casefold()
        return any(word.casefold() in lowered for word in words)
