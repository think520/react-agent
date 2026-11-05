"""W1 E6：掌握度引擎 —— **纯函数**。

路线的设计：近 5 次加权 + 置信帽 {1: 0.5, 2: 0.8} + next_objective 优先级
（挂起问题 > 到期复习 > 第一个未掌握点）。

为什么坚持纯函数：核对时发现掌握度只能在旧值上做增量加减（+0.1 / +0.2 / −0.2），
既不可回放、也没法单测。这里输入"历史与候选"，输出"分数与下一步"，不碰数据库。
逐次作答由 «LearningStore.record_mastery_attempt» 持久化（E6 第一步）。
"""

from __future__ import annotations

from typing import Any, Iterable

from .schema import (
    MASTERY_LEARNING,
    MASTERY_MASTERED,
    MASTERY_NEEDS_REVIEW,
    MASTERY_UNSEEN,
)

# E6.2：推导算法的版本号。历史可回放，结果要能说明是哪一版算出来的 ——
# 改权重、改阈值、改三态处理都必须同时改这个字符串。
MASTERY_ALGORITHM_VERSION = "weighted-window/v1"

# 近 5 次，新 → 旧（越近权重越大）。
ATTEMPT_WEIGHTS: tuple[float, ...] = (0.4, 0.25, 0.15, 0.12, 0.08)

# 「已掌握」要求连续几次**完全答对**（partial 打断连续，见 E15 三态口径）。
MASTERED_STREAK = 2

# 置信缩放：证据越少，越不许声称"掌握"。3 次及以上才允许满分。
# 注意这里是**按比例打折**而不是单纯取上界 —— 若取上界，单次答对与单次"基本正确"
# 会撞到同一个数值（都是 0.5），把两者的差别抹掉。
CONFIDENCE_SCALE: dict[int, float] = {0: 0.0, 1: 0.5, 2: 0.8}

# "基本正确"给半分：既不是答对，也不是答错（与 E15 三态口径一致）。
PARTIAL_CREDIT = 0.5


def _credit(attempt: dict[str, Any]) -> float:
    if str(attempt.get("verdict") or "") == "partial":
        return PARTIAL_CREDIT
    return 1.0 if int(attempt.get("is_correct") or 0) else 0.0


def weighted_mastery(attempts: Iterable[dict[str, Any]]) -> float:
    """由**历史**算掌握度（0..1）。«attempts» 新 → 旧；只看最近 5 次。

    置信帽不是装饰：只答对过一次的概念，分数最高 0.5 —— 界面与调度都不该
    把它当成"已掌握"。
    """
    window = list(attempts)[: len(ATTEMPT_WEIGHTS)]
    if not window:
        return 0.0
    weights = ATTEMPT_WEIGHTS[: len(window)]
    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.0
    earned = sum(weight * _credit(row) for row, weight in zip(window, weights))
    score = (earned / total_weight) * CONFIDENCE_SCALE.get(len(window), 1.0)
    return round(min(1.0, score), 4)


def _verdict(attempt: dict[str, Any]) -> str:
    return str(attempt.get("verdict") or "").strip().lower()


def _is_full_credit(attempt: dict[str, Any]) -> bool:
    """partial 既不算对也不算错，因此不参与「连续答对」的计数。"""
    if _verdict(attempt) == "partial":
        return False
    return bool(int(attempt.get("is_correct") or 0))


def correct_streak(attempts: Iterable[dict[str, Any]]) -> int:
    """从最新一次往前数，连续「完全答对」的次数。«attempts» 新 → 旧。"""
    streak = 0
    for attempt in attempts:
        if not _is_full_credit(attempt):
            break
        streak += 1
    return streak


def derived_status(attempts: Iterable[dict[str, Any]]) -> str:
    """由作答历史推导业务状态。«attempts» 新 → 旧，空历史返回 «unseen»。

    规则（与调度无关，只看发生了什么）：
    - 连续 2 次完全答对 → mastered
    - 最近一次完全答对（连续只有 1 次）→ learning
    - 最近一次 partial → learning（弱证据，不判错）
    - 最近一次答错 → needs_review

    这条规则刻意与旧计数器的语义对齐（consecutive_correct ≥ 2 → 已掌握），
    区别在于它从事件历史算出来，可回放、可单测，不依赖上一次写入的值。
    """
    rows = list(attempts)
    if not rows:
        return MASTERY_UNSEEN
    streak = correct_streak(rows)
    if streak >= MASTERED_STREAK:
        return MASTERY_MASTERED
    if streak >= 1:
        return MASTERY_LEARNING
    if _verdict(rows[0]) == "partial":
        return MASTERY_LEARNING
    return MASTERY_NEEDS_REVIEW


def next_objective(
    *,
    pending_question: dict[str, Any] | None = None,
    due_reviews: Iterable[dict[str, Any]] | None = None,
    unseen_concepts: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    """下一件该做的事（路线原文的优先级）。

    返回 «{kind, concept?, ...}»；三样都没有就返回 «None»（今天没有必须做的）。
    """
    if pending_question:
        return {
            "kind": "pending_question",
            "interaction_id": pending_question.get("interaction_id", ""),
            "prompt": pending_question.get("prompt", ""),
        }
    for record in due_reviews or []:
        concept = str(record.get("concept") or "").strip()
        if concept:
            return {"kind": "due_review", "concept": concept}
    for concept in unseen_concepts or []:
        name = str(concept or "").strip()
        if name:
            return {"kind": "unseen_concept", "concept": name}
    return None
