"""Progress tracking — 掌握度的读取层。

E6.2 之前这里自己攒一套推断规则（连续 2 次对 = mastered、1 次对 = learning），
与 ``learning.scheduler`` 的计数器、``learning.engine`` 的加权值三套并存。
现在这里只做投影：所有状态与分数都来自 ``learning.contract``，不另算一份。
"""

import logging

from .contract import mastery_state, mastery_states
from .schema import Mastery
from .scheduler import ReviewScheduler
from .store import LearningStore

logger = logging.getLogger(__name__)


class ProgressTracker:
    def __init__(self, store: LearningStore, scheduler: ReviewScheduler):
        self.store = store
        self.scheduler = scheduler

    def update_from_quiz(
        self,
        concepts: list[str],
        is_correct: bool,
        verdict: str | None = None,
        evidence_key: str | None = None,
    ) -> list[Mastery]:
        """Record a quiz result against the schedule and its evidence.

        ``evidence_key`` 是幂等键：同一练习会话里同一道题重复提交只算一条证据。

        After updating, auto-checks if any active plan steps are now fully mastered.
        """
        results = []
        for concept in concepts:
            m = self.scheduler.record_review(concept, is_correct, verdict, evidence_key=evidence_key)
            results.append(m)

        # Auto-infer plan step completion
        if is_correct:
            try:
                from .workflow import PlanWorkflowTracker
                tracker = PlanWorkflowTracker(self.store)
                tracker.check_plan_completion()
            except Exception as e:
                logger.warning("[ProgressTracker] plan completion check failed: %s", e)

        return results

    def get_overview(self) -> dict:
        """Get mastery overview. 状态、均分、最弱/最强全部按推导结果。"""
        states = mastery_states(self.store)
        counts: dict[str, int] = {}
        for item in states:
            counts[item.status] = counts.get(item.status, 0) + 1
        total = len(states)

        avg_mastery = round(sum(item.mastery for item in states) / total, 4) if total else 0.0

        weakest = states[:5]
        strongest = sorted(states, key=lambda item: item.mastery, reverse=True)[:5]

        return {
            "total_concepts": total,
            "by_status": counts,
            "average_mastery": avg_mastery,
            "weakest": [self._brief(item) for item in weakest],
            "strongest": [self._brief(item) for item in strongest],
            "algorithm": states[0].algorithm if states else "",
        }

    @staticmethod
    def _brief(state) -> dict:
        return {
            "concept": state.concept,
            "mastery": state.mastery,
            "status": state.status,
            "status_source": state.status_source,
            "evidence": state.evidence,
        }

    def get_concept_detail(self, concept: str) -> dict | None:
        """Get detailed mastery info for a single concept."""
        if not self.store.get_mastery(concept):
            return None
        state = mastery_state(self.store, concept)
        return {
            "concept": state.concept,
            "status": state.status,
            "status_source": state.status_source,
            "mastery": state.mastery,
            "mastery_source": state.mastery_source,
            "evidence": state.evidence,
            "attempts_total": state.attempts_total,
            "algorithm": state.algorithm,
            "review_count": state.review_count,
            "last_reviewed": state.last_reviewed,
            "next_review": state.next_review,
            "interval_days": state.interval_days,
        }
