"""W1 E6：掌握度引擎 —— **纯函数**。

路线的设计：近 5 次加权 + 置信帽 {1: 0.5, 2: 0.8} + next_objective 优先级
（挂起问题 > 到期复习 > 第一个未掌握点）。

为什么坚持纯函数：核对时发现掌握度只能在旧值上做增量加减（+0.1 / +0.2 / −0.2），
既不可回放、也没法单测。这里输入"历史与候选"，输出"分数与下一步"，不碰数据库。
逐次作答由 «LearningStore.record_mastery_attempt» 持久化（E6 第一步）。
"""

from __future__ import annotations

from typing import Any, Iterable

# 近 5 次，新 → 旧（越近权重越大）。
ATTEMPT_WEIGHTS: tuple[float, ...] = (0.4, 0.25, 0.15, 0.12, 0.08)

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
