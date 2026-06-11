"""Quiz-learning integration — bridges quiz results to memory and mastery.

Records learning effects after each quiz submission:
1. Writes a daily memory entry with quiz result
2. Updates mastery via ProgressTracker (spaced repetition)
3. On session completion, writes summary and marks session complete
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
) -> list[Mastery]:
    """Record quiz result into daily memory and mastery tracking.

    1. Appends a daily memory entry (tags: quiz + concepts)
    2. Updates mastery for each concept via ProgressTracker
    3. Returns updated mastery list

    This function is standalone — no dependency on Agent tool context.
    """
    # 1. Write daily memory
    try:
        from memory.daily import DailyMemoryManager

        status_emoji = "✓" if is_correct else "✗"
        concepts_str = ", ".join(question_concepts) if question_concepts else "无知识点"
        content = (
            f"**做题** [{status_emoji}] 知识点: {concepts_str}\n"
            f"反馈: {feedback}"
        )
        tags = ["quiz"] + question_concepts
        dm = DailyMemoryManager(workspace)
        dm.append(content, tags=tags)
    except Exception as e:
        logger.warning("Failed to write daily memory: %s", e)

    # 2. Update mastery
    store = LearningStore(workspace)
    scheduler = ReviewScheduler(store)
    tracker = ProgressTracker(store, scheduler)
    results = tracker.update_from_quiz(question_concepts, is_correct)

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
    """Write session completion summary to daily memory and mark session complete.

    Returns True if session was completed, False if not all questions answered yet.
    """
    from quiz.store import QuizStore

    answered_ids = {a.question_id for a in attempts}
    if not set(question_ids).issubset(answered_ids):
        return False

    total = len(question_ids)
    correct = sum(1 for a in attempts if a.is_correct)
    rate = round(correct / total * 100) if total else 0

    # Collect weak concepts (from wrong answers)
    weak_concepts = []
    store = QuizStore(workspace)
    for a in attempts:
        if not a.is_correct:
            q = store.get_question(a.question_id)
            if q:
                weak_concepts.extend(q.concepts)
    weak_str = ", ".join(set(weak_concepts)) if weak_concepts else "无"

    summary = (
        f"**练习完成** session={session_id}\n"
        f"共 {total} 题，正确 {correct} 题，正确率 {rate}%\n"
        f"薄弱点: {weak_str}"
    )

    try:
        from memory.daily import DailyMemoryManager
        dm = DailyMemoryManager(workspace)
        dm.append(summary, tags=["quiz", "session_summary", f"session_{session_id}"])
    except Exception as e:
        logger.warning("Failed to write session summary: %s", e)

    store.complete_session(session_id)
    logger.info("Quiz session %d completed: %d/%d (%d%%)", session_id, correct, total, rate)
    return True
