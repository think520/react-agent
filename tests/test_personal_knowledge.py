from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.session import Session
from learning.store import LearningStore
from learning.schema import Mastery
from memory.personal_store import PersonalKnowledgeStore
from service.memory_consolidation import MemoryConsolidationService
from service.memory_service import MemoryService
from tools.memory_tools import request_memory_confirmation


def test_global_knowledge_is_shared_but_library_data_is_isolated(tmp_path):
    home = tmp_path / "home"
    first = PersonalKnowledgeStore(str(tmp_path / "first"), home=str(home))
    second = PersonalKnowledgeStore(str(tmp_path / "second"), home=str(home))

    first.create_item(scope="global", kind="preference", title="讲解偏好", content="先给直觉")
    first.create_item(scope="library", kind="course_insight", title="课程结论", content="RAG 需要检索证据")
    first.record_event(event_type="document_opened", source_type="document", source_id="doc-1")

    assert [item["title"] for item in second.list_items(scope="global")] == ["讲解偏好"]
    assert second.list_items(scope="library") == []
    assert second.list_events() == []


def test_candidate_confirmation_can_change_scope_and_rejection_is_suppressed(tmp_path):
    store = PersonalKnowledgeStore(str(tmp_path / "library"), home=str(tmp_path / "home"))
    candidate = store.add_candidate(
        scope="library", kind="learning_strategy", operation="create",
        title="复习方式", content="先主动回忆再看答案", confidence=.8,
        reason="用户多次采用这个方法",
    )
    item, confirmed = store.confirm_candidate(candidate["id"], {"scope": "global"})

    assert item["scope"] == "global"
    assert confirmed["status"] == "confirmed"

    rejected = store.add_candidate(
        scope="library", kind="study_pattern", operation="create",
        title="晚间学习", content="晚上学习效率更高", confidence=.6,
        reason="对话整理",
    )
    store.reject_candidate(rejected["id"])
    duplicate = store.add_candidate(
        scope="library", kind="study_pattern", operation="create",
        title="晚间学习", content="晚上学习效率更高", confidence=.6,
        reason="再次整理",
    )
    assert duplicate is None


def test_reading_progress_and_events_are_idempotent(tmp_path):
    store = PersonalKnowledgeStore(str(tmp_path / "library"), home=str(tmp_path / "home"))
    store.update_reading_progress("doc-1", 20, opened=True)
    store.update_reading_progress("doc-1", 24, opened=True)
    store.update_reading_progress("doc-1", 35)

    events = store.list_events(limit=20)
    assert len([item for item in events if item["type"] == "document_opened"]) == 1
    progress = [item for item in events if item["type"] == "reading_progress"]
    assert {item["payload"]["progress"] for item in progress} == {20, 30}


def test_personalization_uses_confirmed_knowledge_and_mastery_only(tmp_path):
    workspace = str(tmp_path / "library")
    service = MemoryService(workspace, home=str(tmp_path / "home"))
    service.create_knowledge(
        scope="global", kind="preference", title="讲解方式",
        content="先给直觉，再给定义", pinned=True,
    )
    service.add_candidate(
        scope="library", kind="profile_fact", operation="create",
        title="未确认内容", content="这条不能进入提示词", confidence=.6,
        reason="自动整理",
    )
    LearningStore(workspace).upsert_mastery(Mastery(concept="图算法", status="needs_review", score=.3))

    context = service.personalization_context("请解释图算法")

    assert "先给直觉" in context["content"]
    assert "图算法" in context["content"]
    assert "这条不能进入提示词" not in context["content"]
    assert context["references"][0]["content"] == "先给直觉，再给定义"


def test_memory_confirmation_tool_never_writes_and_refuses_secrets(tmp_path):
    session = Session.new(str(tmp_path))
    result = request_memory_confirmation(
        title="学习习惯", content="复习时先做题", scope="global", session=session,
    )
    service = MemoryService(str(tmp_path))

    assert result.ok is True
    assert result.artifacts[0]["type"] == "memory_confirmation"
    assert service.list_knowledge()["items"] == []

    secret = request_memory_confirmation(
        title="密钥", content="api_key=sk-abcdefghijklmnopqrstuvwxyz", session=session,
    )
    assert secret.ok is False
    assert secret.artifacts == []

    secret_title = request_memory_confirmation(
        title="api_key=sk-abcdefghijklmnopqrstuvwxyz", content="普通说明", session=session,
    )
    assert secret_title.ok is False
    assert secret_title.artifacts == []


def test_stale_revision_cannot_succeed_after_a_concurrent_update(tmp_path, monkeypatch):
    store = PersonalKnowledgeStore(str(tmp_path / "library"), home=str(tmp_path / "home"))
    original = store.create_item(
        scope="library", kind="course_insight", title="RAG", content="需要检索证据",
    )
    current = store.update_item(original["id"], original["revision"], {"content": "需要可信检索证据"})
    monkeypatch.setattr(store, "get_item", lambda _item_id: {**current, "revision": original["revision"]})

    with pytest.raises(RuntimeError, match="knowledge_revision_conflict"):
        store.update_item(original["id"], original["revision"], {"content": "过期写入"})


def test_memory_jobs_preserve_retry_attempts_and_completed_jobs_reset(tmp_path):
    store = PersonalKnowledgeStore(str(tmp_path / "library"), home=str(tmp_path / "home"))
    due = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    job = store.enqueue_job("chat", "session-1", 2, due)
    claimed = store.claim_due_job()
    assert claimed["id"] == job["id"]
    assert claimed["attempts"] == 1

    retry = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(timespec="seconds")
    store.fail_job(job["id"], "failed", retry)
    assert store.get_job(job["id"])["attempts"] == 1

    store.finish_job(job["id"])
    rescheduled = store.enqueue_job("chat", "session-1", 4, due)
    assert rescheduled["attempts"] == 0


def test_memory_consolidation_uses_all_three_retry_delays(tmp_path, monkeypatch):
    workspace = str(tmp_path / "library")
    service = MemoryConsolidationService(
        workspace,
        config={"memory": {"enabled": True}, "session": {"save_dir": ".session"}, "llm": {}},
        home=str(tmp_path / "home"),
    )
    due = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    service.store.enqueue_job("chat", "session-1", 2, due)

    def fail(_job):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(service, "_run_job", fail)
    monkeypatch.setattr(service, "_arm_job", lambda _job: None)

    for expected_attempts in (1, 2, 3):
        if expected_attempts > 1:
            service.store.enqueue_job("chat", "session-1", 2, due)
        assert service.run_due() == 0
        job = service.store.list_jobs()[0]
        assert job["attempts"] == expected_attempts
        assert job["status"] == "pending"

    service.store.enqueue_job("chat", "session-1", 2, due)
    assert service.run_due() == 0
    final = service.store.list_jobs()[0]
    assert final["attempts"] == 4
    assert final["status"] == "failed"
