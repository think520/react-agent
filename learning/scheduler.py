"""Conservative SM-2 spaced repetition scheduler."""

import logging
from datetime import datetime, timezone, timedelta

from .schema import MASTERY_LEARNING, MASTERY_MASTERED, MASTERY_NEEDS_REVIEW, Mastery
from .store import LearningStore

MIN_EASE_FACTOR = 1.3
CORRECT_EASE_INCREMENT = 0.1

logger = logging.getLogger(__name__)


class ReviewScheduler:
    def __init__(self, store: LearningStore):
        self.store = store

    def record_review(self, concept: str, correct: bool) -> Mastery:
        """Record a review result and update the next review date."""
        m = self.store.get_mastery(concept)
        if not m:
            m = Mastery(concept=concept)

        m.last_reviewed = datetime.now(timezone.utc).isoformat()
        m.review_count += 1

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

            if m.consecutive_correct >= 2:
                m.status = MASTERY_MASTERED
                m.score = min(1.0, m.score + 0.2)
            else:
                m.status = MASTERY_LEARNING
                m.score = min(1.0, m.score + 0.1)
        else:
            m.consecutive_correct = 0
            m.interval_days = 1
            m.ease_factor = max(MIN_EASE_FACTOR, m.ease_factor - 0.2)
            m.status = MASTERY_NEEDS_REVIEW
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            m.score = max(0.0, m.score - 0.2)

        self.store.upsert_mastery(m)
        return m

    def get_due_concepts(self, limit: int = 20) -> list[Mastery]:
        """Get concepts due for review today."""
        return self.store.get_due_reviews(limit=limit)

    def mark_manual(self, concept: str, status: str) -> Mastery:
        """Manually override mastery status."""
        m = self.store.get_mastery(concept)
        if not m:
            m = Mastery(concept=concept)

        m.status = status
        m.source = "manual"
        m.last_reviewed = datetime.now(timezone.utc).isoformat()

        if status == "mastered":
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
