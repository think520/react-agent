"""W1 E6 收尾：agent 每轮能**读引擎**（D1 的形式是调 «learning_status» 工具）。

D1 原文：掌握度计算与 next_objective 做成无 LLM 的 «learning/engine.py»，
**agent 每轮先调 «learning_status» 工具读引擎**。
引擎与队列接线上一轮已交付；这里补上工具这一格，并把它加进 Web 白名单
（Web 侧工具是白名单制，不加等于不存在）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from learning.schema import Mastery
from learning.store import LearningStore
from tools.learning_tools import learning_status


def _due(store: LearningStore, concept: str, *, score: float = 0.9) -> None:
    store.upsert_mastery(Mastery(
        concept=concept, status="learning", score=score,
        next_review=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    ))


def test_learning_status_reports_the_objective_and_derived_mastery(tmp_path):
    store = LearningStore(str(tmp_path))
    _due(store, "极限")
    store.record_mastery_attempt("极限", True, "correct")

    result = learning_status(workspace=str(tmp_path))

    assert result.ok is True, result
    assert "复习" in result.content and "极限" in result.content, result.content
    # 推导分数（一次证据 → 置信缩放 0.5）与证据条数都要说清楚。
    assert "0.5" in result.content, result.content
    assert "1 次作答记录" in result.content, result.content
    assert result.data["next_objective"]["kind"] == "due_review", result.data


def test_learning_status_labels_a_stored_score_as_such(tmp_path):
    """没有逐次历史的老数据要标注"存量分数"，不冒充推导结果。"""
    store = LearningStore(str(tmp_path))
    _due(store, "老概念", score=0.7)

    result = learning_status(workspace=str(tmp_path))

    assert "0.7" in result.content, result.content
    assert "没有逐次记录" in result.content, result.content
    assert result.data["mastery"][0]["mastery_source"] == "stored", result.data


def test_learning_status_is_honest_when_nothing_is_waiting(tmp_path):
    store = LearningStore(str(tmp_path))
    store.upsert_mastery(Mastery(concept="已掌握", status="mastered", score=1.0))

    result = learning_status(workspace=str(tmp_path))

    assert result.ok is True, result
    assert "今天没有必须做的" in result.content, result.content
    assert result.data["next_objective"] is None, result.data


def test_the_web_agent_can_read_learning_status():
    from web.backend.routers.chat import _WEB_TOOL_NAMES

    assert "learning_status" in _WEB_TOOL_NAMES
