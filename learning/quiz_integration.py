"""Quiz-learning integration — bridges quiz results to mastery.

Records learning effects after each quiz submission:
Learning events are recorded by ``MemoryService``. Legacy daily Markdown files
remain readable, but new quiz activity no longer writes to them.
"""

import logging

from .schema import Mastery
from .store import LearningStore
from .scheduler import ReviewScheduler
from .progress import ProgressTracker

logger = logging.getLogger(__name__)


def record_quiz_learning_effect(
    workspace: str,
    question_concepts: list[str],
    is_correct: bool,
    feedback: str,
    verdict: str | None = None,
    evidence_key: str | None = None,
) -> list[Mastery]:
    """Record quiz result into mastery tracking.

    Updates the review schedule for each concept and stores one piece of evidence.
    ``evidence_key`` 是幂等键（E6.2）：同一练习会话里同一道题重复提交只算一次证据。

    This function is standalone — no dependency on Agent tool context.
    """
    store = LearningStore(workspace)
    scheduler = ReviewScheduler(store)
    tracker = ProgressTracker(store, scheduler)
    results = tracker.update_from_quiz(
        question_concepts, is_correct, verdict, evidence_key=evidence_key,
    )

    logger.info(
        "Quiz learning effect recorded: concepts=%s correct=%s mastery_updated=%d",
        question_concepts, is_correct, len(results),
    )
    return results


def record_quiz_session_summary(
    workspace: str,
    session_id: int,
    question_ids: list[int],
    attempts: list,
) -> bool:
    """Mark a quiz session complete after all questions have answers.

    Returns True if session was completed, False if not all questions answered yet.
    """
    from quiz.store import QuizStore

    answered_ids = {a.question_id for a in attempts}
    if not set(question_ids).issubset(answered_ids):
        return False

    total = len(question_ids)
    correct = sum(1 for a in attempts if a.is_correct)
    rate = round(correct / total * 100) if total else 0

    store = QuizStore(workspace)
    store.complete_session(session_id)
    logger.info("Quiz session %d completed: %d/%d (%d%%)", session_id, correct, total, rate)
    return True
