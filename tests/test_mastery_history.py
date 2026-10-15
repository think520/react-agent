"""W1 E6 第一步：逐次作答要**落库**，掌握度才可能从历史推导。

核对现状：«Mastery» 只存聚合（review_count / consecutive_correct / score / ease），
每次对错本身不落库 —— 于是「近 5 次加权」这类纯函数引擎无从下手，
«learning/scheduler.py» 只能在旧值上做增量加减（+0.1 / +0.2 / −0.2）。
先把数据补上；引擎（«learning/engine.py»）在下一步。
"""

from __future__ import annotations

from learning.scheduler import ReviewScheduler
from learning.store import LearningStore


def test_record_review_persists_each_attempt(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    scheduler.record_review("极限", correct=True, verdict="correct")
    scheduler.record_review("极限", correct=False, verdict="partial")
    scheduler.record_review("极限", correct=False, verdict="incorrect")

    history = store.recent_mastery_attempts("极限", limit=5)

    # 新 → 旧，并且 verdict 与 is_correct 都留下来了（partial 既不算对也不算错）。
    assert [row["verdict"] for row in history] == ["incorrect", "partial", "correct"], history
    assert [row["is_correct"] for row in history] == [0, 0, 1], history
    assert all(row["created_at"] for row in history), history


def test_history_is_capped_and_newest_first(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    for index in range(7):
        scheduler.record_review("图", correct=index % 2 == 0, verdict="correct" if index % 2 == 0 else "incorrect")

    history = store.recent_mastery_attempts("图", limit=5)

    assert len(history) == 5, history
    # index 6,5,4,3,2（偶数=correct）→ 新到旧正好是 对错对错对；更早的两次被截掉。
    assert [row["verdict"] for row in history] == [
        "correct", "incorrect", "correct", "incorrect", "correct",
    ], history


def test_history_keeps_concepts_apart(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    scheduler.record_review("A", correct=True)
    scheduler.record_review("B", correct=False)

    assert len(store.recent_mastery_attempts("A")) == 1
    assert len(store.recent_mastery_attempts("B")) == 1
    assert store.recent_mastery_attempts("A")[0]["is_correct"] == 1
    assert store.recent_mastery_attempts("B")[0]["is_correct"] == 0
    assert store.recent_mastery_attempts("从来没有过的概念") == []


def test_the_aggregate_still_updates(tmp_path):
    """补历史不能改变既有调度行为（SM-2 聚合照旧）。"""
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    scheduler.record_review("堆", correct=True)
    m = scheduler.record_review("堆", correct=True)

    assert m.review_count == 2, m
    assert m.consecutive_correct == 2, m
    assert m.interval_days == 6, m
    assert m.status == "mastered", m
    assert len(store.recent_mastery_attempts("堆")) == 2
