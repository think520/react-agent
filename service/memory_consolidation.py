"""Debounced background consolidation of chat sessions into memory candidates."""

from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from core.session import Session
from memory.personal_store import KNOWLEDGE_KINDS, KNOWLEDGE_SCOPES, PersonalKnowledgeStore
from service.agent_service import AgentService
from service.memory_service import MemoryService
from service.preference_service import PreferenceService
from service.runtime_service import RuntimeService


logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bobodan-memory")
_SCHEDULE_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()
_TIMERS: dict[str, threading.Timer] = {}

_PROMPT = """You organize personal learning knowledge for Bobodan.

Read only the user-visible conversation below. Return at most 3 useful long-term knowledge candidates.
Do not save passwords, API keys, tokens, health diagnoses, politics, religion, finances, exact location, or inferred personality.
Do not create candidates for the user's display name, answer depth, teaching style, feedback strength, or configured long-term goal; those are structured settings.
Deterministic quiz scores and mastery are stored elsewhere and must not become profile claims.
Use global scope only for durable cross-library preferences or profile facts. Use library scope for course-specific insights and study patterns.
If an existing item should change, use operation=update and its exact target_item_id. Otherwise use create.
Return a strict JSON array with fields: scope, kind, operation, title, content, target_item_id, confidence, reason.
Allowed kinds: preference, goal, profile_fact, learning_strategy, course_insight, study_pattern.

Existing confirmed knowledge:
{existing}

Conversation:
{conversation}
"""


def _parse_array(text: str) -> list[dict]:
    from core.llm_json import parse_llm_array
    return [item for item in parse_llm_array(text) if isinstance(item, dict)]


class MemoryConsolidationService:
    def __init__(self, workspace: str, config: dict[str, Any] | None = None,
                 session_dir: str | None = None, legacy_workspace: str | None = None,
                 home: str | None = None):
        self.workspace = workspace
        self.config = config or RuntimeService.load_default_config()
        configured_dir = self.config.get("session", {}).get("save_dir", ".session")
        self.session_dir = session_dir or (
            configured_dir if str(configured_dir).startswith(("/", "\\")) or ":" in str(configured_dir)
            else __import__("os").path.join(workspace, str(configured_dir))
        )
        self.memory = MemoryService(workspace, home=home, legacy_workspace=legacy_workspace)
        self.store = PersonalKnowledgeStore(workspace, home=home)

    def schedule_session(self, session_id: str, message_count: int, delay_seconds: int = 90) -> dict[str, Any]:
        due = datetime.now(timezone.utc) + timedelta(seconds=max(0, delay_seconds))
        job = self.store.enqueue_job("chat", session_id, message_count, due.isoformat(timespec="seconds"))
        self._arm_job(job)
        return job

    def resume_pending(self) -> int:
        self.store.recover_jobs()
        pending = [job for job in self.store.list_jobs(limit=500) if job.get("status") == "pending"]
        for job in pending:
            self._arm_job(job)
        return len(pending)

    def _arm_job(self, job: dict[str, Any]) -> None:
        key = f"{self.store.library_path}:{job['id']}"
        try:
            due = datetime.fromisoformat(str(job["not_before"]).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            due = datetime.now(timezone.utc)
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        delay_seconds = max(0.01, (due - datetime.now(timezone.utc)).total_seconds())
        with _SCHEDULE_LOCK:
            previous = _TIMERS.pop(key, None)
            if previous:
                previous.cancel()
            timer = threading.Timer(delay_seconds, lambda: self._timer_fired(key))
            timer.daemon = True
            _TIMERS[key] = timer
            timer.start()

    def _timer_fired(self, key: str) -> None:
        with _SCHEDULE_LOCK:
            _TIMERS.pop(key, None)
        _EXECUTOR.submit(self.run_due)

    def run_due(self) -> int:
        with _RUN_LOCK:
            completed = 0
            while True:
                job = self.store.claim_due_job()
                if not job:
                    break
                try:
                    self._run_job(job)
                    self.store.finish_job(job["id"], int(job.get("cursor") or 0))
                    completed += 1
                except Exception as exc:
                    logger.warning("Memory consolidation failed for %s: %s", job.get("source_id"), exc)
                    attempts = int(job.get("attempts") or 1)
                    delays = {1: 60, 2: 300, 3: 1800}
                    retry_at = None
                    if attempts in delays:
                        retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delays[attempts])).isoformat(timespec="seconds")
                    self.store.fail_job(job["id"], str(exc), retry_at, int(job.get("cursor") or 0))
                    if retry_at:
                        pending = self.store.get_job(job["id"])
                        if pending:
                            self._arm_job(pending)
                    break
            return completed

    def consolidate_now(self, session_id: str | None = None) -> dict[str, Any]:
        if not self._memory_enabled():
            return {"ok": False, "error": "Learning memory is disabled."}
        if session_id:
            loaded = AgentService.load_session(session_id, self.session_dir)
            if not loaded.get("ok"):
                return {"ok": False, "error": loaded.get("error", "Session not found")}
            with _RUN_LOCK:
                before = len(self.store.list_candidates())
                created = self._consolidate_session(loaded["session"])
                return {"ok": True, "created": created, "candidate_count": len(self.store.list_candidates()) - before}
        completed = self.run_due()
        return {"ok": True, "completed_jobs": completed}

    def _run_job(self, job: dict[str, Any]) -> None:
        if not self._memory_enabled():
            return
        if job.get("source_type") != "chat":
            return
        loaded = AgentService.load_session(str(job["source_id"]), self.session_dir)
        if not loaded.get("ok"):
            raise FileNotFoundError(loaded.get("error", "Session not found"))
        self._consolidate_session(loaded["session"])

    def _consolidate_session(self, session: Session) -> list[dict]:
        visible = []
        evidence = []
        for index, message in enumerate(session.messages):
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content or message.get("tool_calls"):
                continue
            visible.append(f"[{role} #{index}] {content[:4000]}")
            evidence.append({
                "source_type": "chat", "source_id": session.session_id,
                "locator": str(index), "excerpt": content[:240],
            })
        if not any(line.startswith("[user") for line in visible):
            return []
        provider = RuntimeService.create_provider(self.config)
        existing_items = self.store.list_items(limit=20)
        existing = "\n".join(
            f"- id={item['id']} [{item['scope']}/{item['kind']}] {item['title']}: {item['content'][:500]}"
            for item in existing_items
        ) or "(none)"
        prompt = _PROMPT.format(existing=existing, conversation="\n\n".join(visible)[-12000:])
        parsed: list[dict] = []
        for attempt in range(2):
            suffix = "\nReturn only the JSON array." if attempt else ""
            response = provider.complete([{"role": "user", "content": prompt + suffix}])
            parsed = _parse_array(response.content if hasattr(response, "content") else str(response))
            if parsed:
                break
        created = []
        for raw in parsed[:3]:
            scope = str(raw.get("scope") or "library")
            kind = str(raw.get("kind") or "course_insight")
            operation = str(raw.get("operation") or "create")
            title = str(raw.get("title") or "").strip()[:120]
            content = str(raw.get("content") or "").strip()[:5000]
            if scope not in KNOWLEDGE_SCOPES or kind not in KNOWLEDGE_KINDS or operation not in {"create", "update"}:
                continue
            candidate_text = f"{title}\n{content}"
            if not title or not content or self.memory.contains_secret(candidate_text) or self.memory.is_sensitive(candidate_text):
                continue
            target = str(raw.get("target_item_id") or "") or None
            if operation == "update" and not (target and self.store.get_item(target)):
                operation = "create"
                target = None
            result = self.memory.add_candidate(
                scope=scope, kind=kind, operation=operation, title=title, content=content,
                target_item_id=target, confidence=float(raw.get("confidence") or 0.5),
                reason=str(raw.get("reason") or "整理自学习对话")[:1000],
                evidence=evidence[:10], generated_by="session_consolidation",
            )
            if result.get("candidate"):
                created.append(result["candidate"])
        self.memory.record_event(
            event_type="chat_completed", source_type="chat", source_id=session.session_id,
            payload={"message_count": len(session.messages), "candidate_count": len(created)},
            dedupe_key=f"chat_completed:{session.session_id}:{len(session.messages)}",
        )
        return created

    def _memory_enabled(self) -> bool:
        default_provider = self.config.get("llm", {}).get("default_provider", "")
        preferences = PreferenceService(default_provider, []).get()
        return bool(
            self.config.get("memory", {}).get("enabled", True)
            and preferences.get("memory", {}).get("enabled", True)
        )
