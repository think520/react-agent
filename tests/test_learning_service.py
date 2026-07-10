"""Tests for LearningService — service layer for learning plans, progress, and reviews."""

import os
import pytest

from learning.schema import LearningPlan, Mastery
from learning.store import LearningStore
from service.learning_service import LearningService


@pytest.fixture
def workspace(tmp_path):
    return str(tmp_path)


@pytest.fixture
def svc(workspace):
    return LearningService(workspace)


@pytest.fixture
def store(workspace):
    return LearningStore(workspace)


def _make_plan(store, topics_per_step=None):
    if topics_per_step is None:
        topics_per_step = [
            (1, ["进程调度", "死锁"], ["学习进程调度算法", "做 3 道练习题"]),
            (2, ["内存管理"], ["学习虚拟内存", "做 3 道练习题"]),
        ]
    steps = []
    for day, topics, tasks in topics_per_step:
        steps.append({"day": day, "topics": topics, "tasks": tasks, "materials": [], "review": []})
    plan = LearningPlan(title="测试计划", goal="掌握操作系统", steps=steps)
    plan.id = store.save_plan(plan)
    return plan


# --- get_progress ---

def test_get_progress_overview_empty(svc):
    result = svc.get_progress()
    assert result["ok"]
    assert result["total_concepts"] == 0


def test_get_progress_overview_with_data(store, svc):
    store.upsert_mastery(Mastery(concept="A", status="mastered", score=1.0))
    store.upsert_mastery(Mastery(concept="B", status="learning", score=0.5))

    result = svc.get_progress()
    assert result["ok"]
    assert result["total_concepts"] == 2
    assert 0 < result["average_score"] < 1


def test_get_progress_concept_found(store, svc):
    store.upsert_mastery(Mastery(concept="进程调度", status="mastered", score=0.9))

    result = svc.get_progress(concept="进程调度")
    assert result["ok"]
    assert result["concept"] == "进程调度"
    assert result["status"] == "mastered"
    assert result["score"] == 0.9


def test_get_progress_concept_not_found(svc):
    result = svc.get_progress(concept="不存在")
    assert not result["ok"]
    assert "未找到" in result["error"]


# --- get_due_reviews ---

def test_get_due_reviews_empty(svc):
    result = svc.get_due_reviews()
    assert result["ok"]
    assert result["count"] == 0
    assert result["concepts"] == []


def test_get_due_reviews_with_due(store, svc):
    from datetime import datetime, timezone, timedelta
    m = Mastery(
        concept="A", status="learning", score=0.5,
        next_review=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    )
    store.upsert_mastery(m)

    result = svc.get_due_reviews()
    assert result["ok"]
    assert result["count"] == 1
    assert result["concepts"][0]["concept"] == "A"


def test_get_review_queue_aggregates_learning_and_quiz_data(store, svc, monkeypatch):
    from datetime import datetime, timezone, timedelta
    store.upsert_mastery(Mastery(
        concept="A",
        status="learning",
        score=0.5,
        next_review=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    ))
    monkeypatch.setattr(
        "service.quiz_service.QuizService.get_wrong_answer_book",
        lambda self, limit: {"ok": True, "entries": [{"question_id": 1}]},
    )
    monkeypatch.setattr(
        "service.quiz_service.QuizService.get_weakness_analysis",
        lambda self: {"ok": True, "analysis": [{"concept": "A"}]},
    )

    result = svc.get_review_queue()
    assert result["due_concepts"][0]["concept"] == "A"
    assert result["wrong_answers"] == [{"question_id": 1}]
    assert result["weaknesses"] == [{"concept": "A"}]


# --- mark_mastery ---

def test_mark_mastery(svc):
    result = svc.mark_mastery("新知识点", "mastered")
    assert result["ok"]
    assert result["concept"] == "新知识点"
    assert result["status"] == "mastered"
    assert result["score"] >= 0.8


def test_mark_mastery_learning(svc):
    result = svc.mark_mastery("另一个知识点", "learning")
    assert result["ok"]
    assert result["status"] == "learning"


def test_mark_mastery_invalid_status(svc):
    result = svc.mark_mastery("X", "invalid")
    assert not result["ok"]
    assert "Invalid status" in result["error"]


# --- list_plans ---

def test_list_plans_empty(svc):
    result = svc.list_plans()
    assert result["ok"]
    assert result["plans"] == []


def test_list_plans_with_data(store, svc):
    _make_plan(store)
    result = svc.list_plans()
    assert result["ok"]
    assert len(result["plans"]) == 1
    p = result["plans"][0]
    assert p["title"] == "测试计划"
    assert p["days"] == 2
    assert p["status"] == "active"


def test_list_plans_shows_completed(store, svc):
    plan = _make_plan(store)
    store.update_plan_status(plan.id, status="completed")
    result = svc.list_plans()
    assert result["plans"][0]["status"] == "completed"


# --- get_today_tasks ---

def test_get_today_tasks_empty(svc):
    result = svc.get_today_tasks()
    assert result["ok"]
    assert result["plans"] == []
    assert result["reviews"] == []


def test_get_today_tasks_shows_incomplete(store, svc):
    _make_plan(store)
    store.mark_task_done(1, 1, 0, source="manual")

    result = svc.get_today_tasks()
    assert result["ok"]
    assert len(result["plans"]) == 1
    # Step 1: 1 remaining, Step 2: 2 remaining
    assert len(result["plans"][0]["steps"]) == 2


def test_get_today_tasks_empty_when_all_done(store, svc):
    plan = _make_plan(store)
    store.mark_step_done(plan.id, 1, 2)
    store.mark_step_done(plan.id, 2, 2)

    result = svc.get_today_tasks()
    assert result["ok"]
    assert len(result["plans"]) == 0


# --- get_plan_progress ---

def test_get_plan_progress(store, svc):
    plan = _make_plan(store)
    store.mark_task_done(plan.id, 1, 0, source="manual")

    result = svc.get_plan_progress(plan.id)
    assert result["ok"]
    assert result["total_tasks"] == 4
    assert result["done_tasks"] == 1
    assert result["progress_pct"] == 25


def test_get_plan_progress_nonexistent(svc):
    result = svc.get_plan_progress(999)
    assert not result["ok"]
    assert "未找到" in result["error"]


# --- complete_task ---

def test_complete_task(store, svc):
    plan = _make_plan(store)
    result = svc.complete_task(plan.id, 1, 0)
    assert result["ok"]
    assert store.is_task_done(plan.id, 1, 0)


def test_complete_task_nonexistent_plan(svc):
    result = svc.complete_task(999, 1, 0)
    assert not result["ok"]
    assert "未找到" in result["error"]


def test_complete_task_invalid_day(store, svc):
    plan = _make_plan(store)
    result = svc.complete_task(plan.id, 99, 0)
    assert not result["ok"]
    assert "没有第 99 天" in result["error"]


def test_complete_task_invalid_index(store, svc):
    plan = _make_plan(store)
    result = svc.complete_task(plan.id, 1, 99)
    assert not result["ok"]
    assert "越界" in result["error"]


def test_complete_task_marks_plan_completed_on_last(store, svc):
    plan = _make_plan(store)
    store.mark_task_done(plan.id, 1, 0, source="manual")
    store.mark_task_done(plan.id, 1, 1, source="manual")
    store.mark_task_done(plan.id, 2, 0, source="manual")
    # Last task
    result = svc.complete_task(plan.id, 2, 1)
    assert result["ok"]
    assert store.get_plan(plan.id).status == "completed"


# --- complete_step ---

def test_complete_step(store, svc):
    plan = _make_plan(store)
    result = svc.complete_step(plan.id, 1)
    assert result["ok"]
    assert store.is_task_done(plan.id, 1, 0)
    assert store.is_task_done(plan.id, 1, 1)


def test_complete_step_nonexistent_plan(svc):
    result = svc.complete_step(999, 1)
    assert not result["ok"]
    assert "未找到" in result["error"]


def test_complete_step_invalid_day(store, svc):
    plan = _make_plan(store)
    result = svc.complete_step(plan.id, 99)
    assert not result["ok"]
    assert "没有第 99 天" in result["error"]


def test_complete_step_marks_plan_completed_on_last(store, svc):
    plan = _make_plan(store)
    store.mark_step_done(plan.id, 1, 2, source="manual")
    # Last step
    result = svc.complete_step(plan.id, 2)
    assert result["ok"]
    assert store.get_plan(plan.id).status == "completed"


# --- Data contract ---

def test_all_results_have_ok_field(svc, store):
    _make_plan(store)
    store.upsert_mastery(Mastery(concept="X", status="mastered", score=1.0))

    methods = [
        svc.get_progress(),
        svc.get_progress(concept="X"),
        svc.get_due_reviews(),
        svc.mark_mastery("Y", "learning"),
        svc.list_plans(),
        svc.get_today_tasks(),
        svc.get_plan_progress(1),
        svc.complete_task(1, 1, 0),
        svc.complete_step(1, 2),
    ]
    for r in methods:
        assert "ok" in r, f"Missing 'ok' in {r}"
