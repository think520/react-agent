"""W1 E6 接线：把纯函数引擎接到复习队列与「今天该做什么」。

引擎（«learning/engine.py»）与逐次历史（«mastery_attempts»）已经交付；
这一步让界面真的用上它 —— 而且要说清「这个分数是**推导**出来的还是老数据里的存量」。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from learning.schema import Mastery
from learning.store import LearningStore
from service.learning_service import LearningService


def _due_concept(store: LearningStore, concept: str, *, score: float = 0.9) -> None:
    store.upsert_mastery(Mastery(
        concept=concept,
        status="learning",
        score=score,
        next_review=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    ))


def test_review_queue_derives_mastery_from_history(tmp_path):
    store = LearningStore(str(tmp_path))
    _due_concept(store, "极限")
    # 一次答对：置信缩放 0.5（一次证据不足以声称掌握）。
    store.record_mastery_attempt("极限", True, "correct")

    queue = LearningService(str(tmp_path)).get_review_queue()
    item = next(entry for entry in queue["due_concepts"] if entry["concept"] == "极限")

    assert item["mastery"] == 0.5, item
    assert item["evidence"] == 1, item
    assert item["mastery_source"] == "history", item


def test_review_queue_falls_back_to_the_stored_score_without_history(tmp_path):
    """老数据没有逐次历史 —— 退回存量分数，并且**如实标注**来源。"""
    store = LearningStore(str(tmp_path))
    _due_concept(store, "老概念", score=0.7)

    queue = LearningService(str(tmp_path)).get_review_queue()
    item = next(entry for entry in queue["due_concepts"] if entry["concept"] == "老概念")

    assert item["mastery"] == 0.7, item
    assert item["evidence"] == 0, item
    assert item["mastery_source"] == "stored", item


def test_next_objective_prefers_a_pending_question(tmp_path):
    from service.interaction_service import InteractionService

    store = LearningStore(str(tmp_path))
    _due_concept(store, "到期概念")
    InteractionService(str(tmp_path)).register(
        "i1", chat_session_id="c1",
        questions=[{"id": "q1", "prompt": "先学哪个？", "options": ["甲", "乙"]}],
    )

    objective = LearningService(str(tmp_path)).get_next_objective()

    assert objective["kind"] == "pending_question", objective
    assert objective["interaction_id"] == "i1", objective


def test_next_objective_prefers_due_reviews_over_unmastered(tmp_path):
    store = LearningStore(str(tmp_path))
    _due_concept(store, "到期概念")
    store.upsert_mastery(Mastery(concept="没到期的", status="learning", score=0.2))

    objective = LearningService(str(tmp_path)).get_next_objective()

    assert objective["kind"] == "due_review", objective
    assert objective["concept"] == "到期概念", objective


def test_next_objective_falls_back_to_the_weakest_unmastered_concept(tmp_path):
    store = LearningStore(str(tmp_path))
    store.upsert_mastery(Mastery(concept="还行", status="learning", score=0.6))
    store.upsert_mastery(Mastery(concept="最弱", status="needs_review", score=0.1))
    store.upsert_mastery(Mastery(concept="已掌握", status="mastered", score=1.0))

    objective = LearningService(str(tmp_path)).get_next_objective()

    assert objective["kind"] == "unseen_concept", objective
    assert objective["concept"] == "最弱", objective


def test_next_objective_is_none_when_nothing_is_waiting(tmp_path):
    store = LearningStore(str(tmp_path))
    store.upsert_mastery(Mastery(concept="已掌握", status="mastered", score=1.0))

    assert LearningService(str(tmp_path)).get_next_objective() is None


def test_review_queue_includes_the_next_objective(tmp_path):
    store = LearningStore(str(tmp_path))
    _due_concept(store, "到期概念")

    queue = LearningService(str(tmp_path)).get_review_queue()

    assert queue["next_objective"]["kind"] == "due_review", queue.get("next_objective")
