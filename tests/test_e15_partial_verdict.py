"""E15 regression: partial short answers are three-state end to end.

Covers the two inconsistencies found in the A0 reconciliation:
1. mastery mapping treated "partial" as a failure (is_correct=False -> needs_review);
2. the attempt did not persist the verdict, so the recap could not show it.
"""

from __future__ import annotations

from learning.progress import ProgressTracker
from learning.scheduler import ReviewScheduler
from learning.store import LearningStore


def test_partial_verdict_keeps_concept_in_learning(tmp_path):
    store = LearningStore(str(tmp_path))
    tracker = ProgressTracker(store, ReviewScheduler(store))

    results = tracker.update_from_quiz(["极限"], is_correct=False, verdict="partial")

    assert len(results) == 1
    assert results[0].status == "learning"
    assert results[0].interval_days == 1
    assert results[0].consecutive_correct == 0


def test_incorrect_verdict_still_resets_to_needs_review(tmp_path):
    store = LearningStore(str(tmp_path))
    tracker = ProgressTracker(store, ReviewScheduler(store))

    results = tracker.update_from_quiz(["极限"], is_correct=False, verdict="incorrect")

    assert results[0].status == "needs_review"


def test_partial_does_not_compound_into_mastery(tmp_path):
    store = LearningStore(str(tmp_path))
    tracker = ProgressTracker(store, ReviewScheduler(store))

    tracker.update_from_quiz(["极限"], is_correct=False, verdict="partial")
    again = tracker.update_from_quiz(["极限"], is_correct=False, verdict="partial")

    assert again[0].status == "learning"
    assert again[0].consecutive_correct == 0
