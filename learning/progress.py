"""Progress tracking — syncs quiz results to mastery state.

Auto-infers mastery from quiz attempts:
- 2+ consecutive correct → mastered
- 1 correct → learning
- Wrong → needs_review

Also supports manual overrides via scheduler.mark_manual().
"""

from .schema import Mastery
from .store import LearningStore
from .scheduler import ReviewScheduler


class ProgressTracker:
    def __init__(self, store: LearningStore, scheduler: ReviewScheduler):
        self.store = store
        self.scheduler = scheduler

    def update_from_quiz(self, concepts: list[str], is_correct: bool) -> list[Mastery]:
        """Update mastery for each concept based on quiz result."""
        results = []
        for concept in concepts:
            m = self.scheduler.record_review(concept, is_correct)
            results.append(m)
        return results

    def get_overview(self) -> dict:
        """Get mastery overview across all concepts."""
        counts = self.store.count_by_status()
        total = sum(counts.values())
        all_mastery = self.store.list_mastery(limit=500)

        avg_score = sum(m.score for m in all_mastery) / total if total > 0 else 0.0

        weakest = sorted(all_mastery, key=lambda m: m.score)[:5]
        strongest = sorted(all_mastery, key=lambda m: m.score, reverse=True)[:5]

        return {
            "total_concepts": total,
            "by_status": counts,
            "average_score": round(avg_score, 2),
            "weakest": [{"concept": m.concept, "score": round(m.score, 2), "status": m.status} for m in weakest],
            "strongest": [{"concept": m.concept, "score": round(m.score, 2), "status": m.status} for m in strongest],
        }

    def get_concept_detail(self, concept: str) -> dict | None:
        """Get detailed mastery info for a single concept."""
        m = self.store.get_mastery(concept)
        if not m:
            return None
        return {
            "concept": m.concept,
            "status": m.status,
            "score": round(m.score, 2),
            "review_count": m.review_count,
            "consecutive_correct": m.consecutive_correct,
            "last_reviewed": m.last_reviewed,
            "next_review": m.next_review,
            "source": m.source,
        }
