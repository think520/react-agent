"""Simple spaced repetition scheduler.

Review intervals: 1 day, 3 days, 7 days, 14 days.
On correct answer: advance to next interval.
On wrong answer: reset to first interval.

Future upgrade path: Ebbinghaus forgetting curve + mastery-weighted intervals.
"""

from datetime import datetime, timezone, timedelta

from .schema import Mastery
from .store import LearningStore

INTERVALS_DAYS = [1, 3, 7, 14]


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
            # Determine interval index based on consecutive correct count
            idx = min(m.consecutive_correct - 1, len(INTERVALS_DAYS) - 1)
            days = INTERVALS_DAYS[idx]
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

            if m.consecutive_correct >= 2:
                m.status = "mastered"
                m.score = min(1.0, m.score + 0.2)
            else:
                m.status = "learning"
                m.score = min(1.0, m.score + 0.1)
        else:
            m.consecutive_correct = 0
            m.status = "needs_review"
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
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        elif status == "needs_review":
            m.score = min(m.score, 0.3)
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        elif status == "learning":
            m.next_review = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        self.store.upsert_mastery(m)
        return m
