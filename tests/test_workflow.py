"""Tests for P3 Workflow Runtime: plan_progress, auto-inference, /learning today."""

import os
import pytest

from learning.schema import LearningPlan, Mastery
from learning.store import LearningStore
from learning.workflow import PlanWorkflowTracker


@pytest.fixture
def store(tmp_path):
    return LearningStore(str(tmp_path))


@pytest.fixture
def tracker(store):
    return PlanWorkflowTracker(store)


def _make_plan(store, topics_per_step=None):
    """Create a plan with steps. topics_per_step: list of (day, topics, tasks)."""
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


# --- Plan Progress CRUD ---

def test_mark_task_done(store):
    plan = _make_plan(store)
    store.mark_task_done(plan.id, 1, 0, source="manual")
    assert store.is_task_done(plan.id, 1, 0)
    assert not store.is_task_done(plan.id, 1, 1)


def test_mark_step_done(store):
    plan = _make_plan(store)
    store.mark_step_done(plan.id, 1, 2, source="manual")
    assert store.is_task_done(plan.id, 1, 0)
    assert store.is_task_done(plan.id, 1, 1)


def test_get_progress(store):
    plan = _make_plan(store)
    store.mark_task_done(plan.id, 1, 0)
    store.mark_task_done(plan.id, 1, 1)
    progress = store.get_progress(plan.id)
    assert len(progress) == 2
    assert (1, 0) in progress
    assert (1, 1) in progress


def test_update_plan_status(store):
    plan = _make_plan(store)
    assert plan.status == "active"
    store.update_plan_status(plan.id, status="completed")
    updated = store.get_plan(plan.id)
    assert updated.status == "completed"


def test_update_plan_current_day(store):
    plan = _make_plan(store)
    store.update_plan_status(plan.id, current_day=2)
    updated = store.get_plan(plan.id)
    assert updated.current_day == 2


def test_get_active_plans(store):
    plan1 = _make_plan(store)
    plan2 = _make_plan(store)
    store.update_plan_status(plan1.id, status="completed")

    active = store.get_active_plans()
    assert len(active) == 1
    assert active[0].id == plan2.id


# --- Schema migration ---

def test_plan_has_status_field(store):
    plan = _make_plan(store)
    fetched = store.get_plan(plan.id)
    assert fetched.status == "active"
    assert fetched.current_day is None


# --- Auto-inference ---

def test_auto_complete_step_when_topics_mastered(store, tracker):
    plan = _make_plan(store)

    # Mark both topics as mastered
    store.upsert_mastery(Mastery(concept="进程调度", status="mastered", score=1.0))
    store.upsert_mastery(Mastery(concept="死锁", status="mastered", score=1.0))

    results = tracker.check_plan_completion()

    assert len(results) == 1
    assert results[0]["step_day"] == 1
    assert store.is_task_done(plan.id, 1, 0)
    assert store.is_task_done(plan.id, 1, 1)


def test_no_auto_complete_when_topic_not_mastered(store, tracker):
    _make_plan(store)

    # Only one topic mastered
    store.upsert_mastery(Mastery(concept="进程调度", status="mastered", score=1.0))
    store.upsert_mastery(Mastery(concept="死锁", status="learning", score=0.5))

    results = tracker.check_plan_completion()
    assert len(results) == 0


def test_no_auto_complete_when_already_done(store, tracker):
    plan = _make_plan(store)

    store.upsert_mastery(Mastery(concept="进程调度", status="mastered", score=1.0))
    store.upsert_mastery(Mastery(concept="死锁", status="mastered", score=1.0))

    # First check auto-completes
    tracker.check_plan_completion()

    # Second check should not re-complete
    results = tracker.check_plan_completion()
    assert len(results) == 0


def test_plan_auto_completed_when_all_steps_done(store, tracker):
    plan = _make_plan(store)

    # Master all topics
    for topic in ["进程调度", "死锁", "内存管理"]:
        store.upsert_mastery(Mastery(concept=topic, status="mastered", score=1.0))

    tracker.check_plan_completion()

    updated = store.get_plan(plan.id)
    assert updated.status == "completed"


def test_plan_not_completed_if_one_step_missing(store, tracker):
    plan = _make_plan(store)

    # Only first step topics mastered
    store.upsert_mastery(Mastery(concept="进程调度", status="mastered", score=1.0))
    store.upsert_mastery(Mastery(concept="死锁", status="mastered", score=1.0))

    tracker.check_plan_completion()

    updated = store.get_plan(plan.id)
    assert updated.status == "active"


# --- Progress summary ---

def test_get_plan_progress_summary(store, tracker):
    plan = _make_plan(store)
    store.mark_task_done(plan.id, 1, 0, source="manual")

    summary = tracker.get_plan_progress_summary(plan.id)

    assert summary["plan_id"] == plan.id
    assert summary["total_tasks"] == 4
    assert summary["done_tasks"] == 1
    assert summary["progress_pct"] == 25
    assert summary["steps"][0]["tasks"][0]["done"] is True
    assert summary["steps"][0]["tasks"][1]["done"] is False


def test_get_plan_progress_summary_nonexistent(store, tracker):
    assert tracker.get_plan_progress_summary(999) is None


# --- Today tasks (catch-up mode) ---

def test_get_today_tasks_shows_incomplete(store, tracker):
    plan = _make_plan(store)
    store.mark_task_done(plan.id, 1, 0, source="manual")

    today = tracker.get_today_tasks(os.path.dirname(os.path.dirname(store.db_path)))

    assert len(today["plans"]) == 1
    p = today["plans"][0]
    assert p["plan_id"] == plan.id
    # Step 1 has 1 incomplete task, step 2 has 2 incomplete tasks
    assert len(p["steps"]) == 2
    assert len(p["steps"][0]["tasks"]) == 1  # 1 remaining in step 1
    assert len(p["steps"][1]["tasks"]) == 2  # 2 remaining in step 2


def test_get_today_tasks_empty_when_all_done(store, tracker):
    plan = _make_plan(store)
    store.mark_step_done(plan.id, 1, 2)
    store.mark_step_done(plan.id, 2, 2)

    today = tracker.get_today_tasks(".")
    assert len(today["plans"]) == 0


def test_get_today_tasks_catchup_shows_all_incomplete(store, tracker):
    """Catch-up mode: shows tasks from day 1 and day 2, not just 'today'."""
    plan = _make_plan(store, topics_per_step=[
        (1, ["A"], ["task A1"]),
        (2, ["B"], ["task B1"]),
        (3, ["C"], ["task C1"]),
    ])

    today = tracker.get_today_tasks(".")
    assert len(today["plans"]) == 1
    # All 3 days should show since none are done
    assert len(today["plans"][0]["steps"]) == 3


# --- learning_plan_progress tool ---

def test_learning_plan_progress_status(store):
    from tools.learning_tools import learning_plan_progress
    plan = _make_plan(store)

    result = learning_plan_progress(plan_id=plan.id, action="status", workspace=os.path.dirname(os.path.dirname(store.db_path)))
    assert result.ok
    assert "测试计划" in result.content
    assert "0/4" in result.content


def test_learning_plan_progress_complete_task(store):
    from tools.learning_tools import learning_plan_progress
    plan = _make_plan(store)
    ws = os.path.dirname(os.path.dirname(store.db_path))

    result = learning_plan_progress(plan_id=plan.id, action="complete_task", day=1, task_index=0, workspace=ws)
    assert result.ok
    assert store.is_task_done(plan.id, 1, 0)


def test_learning_plan_progress_complete_step(store):
    from tools.learning_tools import learning_plan_progress
    plan = _make_plan(store)
    ws = os.path.dirname(os.path.dirname(store.db_path))

    result = learning_plan_progress(plan_id=plan.id, action="complete_step", day=1, workspace=ws)
    assert result.ok
    assert store.is_task_done(plan.id, 1, 0)
    assert store.is_task_done(plan.id, 1, 1)


def test_learning_plan_progress_today(store):
    from tools.learning_tools import learning_plan_progress
    _make_plan(store)
    ws = os.path.dirname(os.path.dirname(store.db_path))

    result = learning_plan_progress(plan_id=0, action="today", workspace=ws)
    assert result.ok
    assert "测试计划" in result.content


def test_learning_plan_progress_unknown_action(store):
    from tools.learning_tools import learning_plan_progress
    plan = _make_plan(store)

    result = learning_plan_progress(plan_id=plan.id, action="invalid")
    assert not result.ok
    assert "未知" in result.content


# --- ProgressTracker integration ---

def test_update_from_quiz_triggers_auto_check(tmp_path):
    from learning.progress import ProgressTracker
    from learning.scheduler import ReviewScheduler

    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)

    # Create a plan with topic "进程调度"
    plan = LearningPlan(
        title="test",
        goal="test",
        steps=[{"day": 1, "topics": ["进程调度"], "tasks": ["task 1"], "materials": [], "review": []}],
    )
    plan.id = store.save_plan(plan)

    # First correct → learning (not mastered, no auto-complete)
    progress.update_from_quiz(["进程调度"], is_correct=True)
    assert not store.is_task_done(plan.id, 1, 0)

    # Second correct → mastered (auto-complete kicks in)
    progress.update_from_quiz(["进程调度"], is_correct=True)
    assert store.is_task_done(plan.id, 1, 0)
