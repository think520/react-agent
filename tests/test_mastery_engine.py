"""W1 E6 第二步：掌握度引擎是**纯函数**（路线：近 5 次加权 + 置信帽 + next_objective 优先级）。

为什么是纯函数：核对时发现旧实现只能在旧值上做增量加减（+0.1/+0.2/−0.2），
既不可回放也不可测试。输入历史、输出分数与下一步 —— 不碰数据库。
"""

from __future__ import annotations

from learning.engine import next_objective, weighted_mastery


def attempt(is_correct: bool, verdict: str = "") -> dict:
    return {"is_correct": 1 if is_correct else 0, "verdict": verdict}


class TestWeightedMastery:
    def test_no_history_is_zero(self):
        assert weighted_mastery([]) == 0.0

    def test_one_correct_answer_cannot_claim_mastery(self):
        # 置信帽：只有 1 次证据时最高 0.5。
        assert weighted_mastery([attempt(True)]) == 0.5

    def test_two_correct_answers_cap_at_point_eight(self):
        assert weighted_mastery([attempt(True), attempt(True)]) == 0.8

    def test_three_correct_answers_reach_one(self):
        assert weighted_mastery([attempt(True), attempt(True), attempt(True)]) == 1.0

    def test_recent_results_weigh_more(self):
        # 同样"对一半"，最近答对的那次应该更高。
        improving = weighted_mastery([attempt(True), attempt(False)])
        slipping = weighted_mastery([attempt(False), attempt(True)])
        assert improving > slipping, (improving, slipping)

    def test_partial_counts_as_half_credit(self):
        assert weighted_mastery([attempt(False, "partial")]) == 0.25
        assert weighted_mastery([attempt(False, "partial"), attempt(False, "partial")]) == 0.4

    def test_only_the_last_five_matter(self):
        # 更早的错题不该继续压着现在的分数。
        recent = [attempt(True)] * 5
        with_old_failures = recent + [attempt(False)] * 5
        assert weighted_mastery(with_old_failures) == weighted_mastery(recent) == 1.0


class TestNextObjective:
    def test_pending_question_wins(self):
        objective = next_objective(
            pending_question={"interaction_id": "i1", "prompt": "先学哪个？"},
            due_reviews=[{"concept": "到期概念"}],
            unseen_concepts=["未掌握概念"],
        )
        assert objective["kind"] == "pending_question", objective

    def test_due_review_beats_unseen(self):
        objective = next_objective(
            due_reviews=[{"concept": "到期概念"}],
            unseen_concepts=["未掌握概念"],
        )
        assert objective["kind"] == "due_review", objective
        assert objective["concept"] == "到期概念", objective

    def test_unseen_is_the_last_resort(self):
        objective = next_objective(unseen_concepts=["未掌握概念"])
        assert objective["kind"] == "unseen_concept", objective

    def test_nothing_to_do_returns_none(self):
        assert next_objective() is None
        assert next_objective(due_reviews=[], unseen_concepts=[]) is None
