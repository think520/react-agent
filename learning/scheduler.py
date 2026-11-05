"""Conservative SM-2 spaced repetition scheduler."""

import logging
from datetime import datetime, timezone, timedelta

from .schema import Mastery
from .store import LearningStore

MIN_EASE_FACTOR = 1.3
CORRECT_EASE_INCREMENT = 0.1

logger = logging.getLogger(__name__)


class ReviewScheduler:
    def __init__(self, store: LearningStore):
        self.store = store

    def record_review(
        self,
        concept: str,
        correct: bool,
        verdict: str | None = None,
        evidence_key: str | None = None,
    ) -> Mastery:
        """Record a review result and update the **schedule** only.

        ``verdict`` distinguishes a partial short answer from a failure (E15):
        partial credit keeps the concept in "learning" and schedules a near
        review, instead of resetting it as an error.

        E6.2：这里只写调度（next_review / interval / ease / 连续计数）与一条作答证据，
        不再写「掌握状态」—— 状态是推导结果，由 ``learning.contract`` 从证据算出来。
        旧 status / score 列保留为历史快照，不再被自动路径覆盖。
        """
        m = self.store.get_mastery(concept)
        if not m:
            m = Mastery(concept=concept)

        m.last_reviewed = datetime.now(timezone.utc).isoformat()
        m.review_count += 1
        m.source = "auto"

        if correct:
            m.consecutive_correct += 1
            if m.consecutive_correct == 1:
                m.interval_days = 1
            elif m.consecutive_correct == 2:
                m.interval_days = 6
            else:
                m.interval_days = max(1, round(m.interval_days * m.ease_factor))
            m.ease_factor += CORRECT_EASE_INCREMENT
            m.next_review = (
                datetime.now(timezone.utc) + timedelta(days=m.interval_days)
            ).isoformat()
        elif verdict == "partial":
            # Weak evidence: review again soon, do not penalise ease.
            m.consecutive_correct = 0
            m.interval_days = 1
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        else:
            m.consecutive_correct = 0
            m.interval_days = 1
            m.ease_factor = max(MIN_EASE_FACTOR, m.ease_factor - 0.2)
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        # W1 E6：自动作答在**唯一漏斗**里留一行历史（手动标记不走这里）。
        self.store.record_mastery_attempt(
            concept, correct, verdict or "", evidence_key=evidence_key,
        )
        self.store.upsert_mastery(m)
        return m

    def get_due_concepts(self, limit: int = 20) -> list[Mastery]:
        """Get concepts due for review today."""
        return self.store.get_due_reviews(limit=limit)

    def mark_manual(self, concept: str, status: str) -> Mastery:
        """Manually override mastery status.

        E6.2：用户判断写在 manual_status / manual_at，不与推导结果混存。
        只要之后没有新的作答证据，契约就优先用它；有新证据则推导结果接管，
        并在输出里说清「这次是推导出来的，不是你的标记」。
        """
        m = self.store.get_mastery(concept)
        if not m:
            m = Mastery(concept=concept)

        m.manual_status = status
        m.manual_at = datetime.now(timezone.utc).isoformat()
        m.source = "manual"
        m.last_reviewed = m.manual_at

        if status == "mastered":
            # score 只是「没有逐次历史时」的回退估计，不参与有历史时的推导。
            m.score = max(m.score, 0.8)
            m.interval_days = max(m.interval_days, 14)
            m.next_review = (
                datetime.now(timezone.utc) + timedelta(days=m.interval_days)
            ).isoformat()
        elif status == "needs_review":
            m.score = min(m.score, 0.3)
            m.interval_days = 1
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        elif status == "learning":
            m.interval_days = 1
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        self.store.upsert_mastery(m)
        if status == "mastered":
            try:
                from .workflow import PlanWorkflowTracker
                PlanWorkflowTracker(self.store).check_plan_completion()
            except Exception as e:
                logger.warning("[ReviewScheduler] plan completion check failed: %s", e)
        return m
