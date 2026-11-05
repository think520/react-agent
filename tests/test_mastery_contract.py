"""E6.2：掌握度统一消费契约的回归。

这一组用例锁住四件事：

1. **可回放** —— 同一份作答历史，无论算多少次都得到同一个状态与分数，且带算法版本。
2. **三件事分开** —— 事实（证据）、估计（掌握度/状态）、调度（下次复习）各归各的；
   同一次作答只产生一条证据，反复答同一道题不会把掌握度推上去。
3. **手动与推断分开** —— 用户标记优先，但之后出现新证据时推导结果接管，并且说清是谁说的。
4. **一个结论** —— 进度、复习队列、手动标记、计划完成判定读到的是同一个判断。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from learning.contract import mastery_state, mastery_states
from learning.engine import MASTERY_ALGORITHM_VERSION
from learning.progress import ProgressTracker
from learning.scheduler import ReviewScheduler
from learning.schema import LearningPlan, Mastery
from learning.store import LearningStore


def _store(tmp_path) -> LearningStore:
    return LearningStore(str(tmp_path))


def _answer(store: LearningStore, concept: str, correct: bool, verdict: str = "", key: str | None = None):
    scheduler = ReviewScheduler(store)
    return scheduler.record_review(concept, correct, verdict, evidence_key=key)


def _due(store: LearningStore, concept: str, *, score: float = 0.9, status: str = "learning") -> None:
    store.upsert_mastery(Mastery(
        concept=concept,
        status=status,
        score=score,
        next_review=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    ))


# --- 1. 可回放 ---

def test_the_same_history_always_derives_the_same_state(tmp_path):
    store = _store(tmp_path)
    for correct, verdict in ((True, "correct"), (False, "partial"), (True, "correct")):
        _answer(store, "极限", correct, verdict)

    first = mastery_state(store, "极限")
    second = mastery_state(store, "极限")

    assert first == second, (first, second)
    assert first.algorithm == MASTERY_ALGORITHM_VERSION
    assert first.evidence == 3


def test_derivation_can_be_replayed_on_a_copied_history(tmp_path):
    """把历史搬到另一份库里，**推导部分**必须一模一样（不依赖写入时的中间值）。

    调度字段（next_review / 间隔 / 复习次数）不在比较范围内 —— 它们是另一件事。
    """
    source = _store(tmp_path / "source")
    for correct, verdict in ((True, "correct"), (True, "correct"), (False, "incorrect")):
        _answer(source, "堆", correct, verdict)

    target = _store(tmp_path / "target")
    for row in reversed(source.recent_mastery_attempts("堆", limit=5)):
        target.record_mastery_attempt("堆", bool(row["is_correct"]), row["verdict"])

    first, second = mastery_state(source, "堆"), mastery_state(target, "堆")
    derived = ("status", "status_source", "mastery", "mastery_source", "evidence", "attempts_total", "algorithm")
    assert {key: getattr(first, key) for key in derived} == {key: getattr(second, key) for key in derived}


# --- 2. 事实、估计、调度分开 ---

def test_one_correct_answer_is_not_mastery(tmp_path):
    store = _store(tmp_path)
    m = _answer(store, "二叉树", True)

    state = mastery_state(store, "二叉树")
    assert state.status == "learning"
    assert state.mastery == 0.5  # 一次证据被置信缩放打折
    assert state.evidence == 1
    # 调度照旧：明天再来一次。
    assert m.interval_days == 1 and state.next_review


def test_two_separate_evidence_rows_make_it_mastered(tmp_path):
    store = _store(tmp_path)
    _answer(store, "堆", True, key="quiz:1:10")
    _answer(store, "堆", True, key="quiz:1:11")

    state = mastery_state(store, "堆")
    assert state.status == "mastered"
    assert state.evidence == 2
    assert state.mastery == 0.8


def test_wrong_then_right_stays_in_learning(tmp_path):
    store = _store(tmp_path)
    _answer(store, "图", False, "incorrect")
    _answer(store, "图", True, "correct")

    state = mastery_state(store, "图")
    assert state.status == "learning"
    assert 0 < state.mastery < 0.5


def test_partial_is_weak_evidence_not_a_failure(tmp_path):
    store = _store(tmp_path)
    _answer(store, "哈希", False, "partial")

    state = mastery_state(store, "哈希")
    assert state.status == "learning"
    assert state.mastery == 0.25  # 半分 × 单次置信 0.5


def test_resubmitting_the_same_question_does_not_add_evidence(tmp_path):
    """同一练习会话里反复答同一道题，只算一条证据 —— 否则刷两遍就"掌握"了。"""
    store = _store(tmp_path)
    key = "quiz:7:42"

    _answer(store, "排序", True, key=key)
    _answer(store, "排序", True, key=key)
    _answer(store, "排序", True, key=key)

    state = mastery_state(store, "排序")
    assert state.evidence == 1, state
    assert state.attempts_total == 1, state
    assert state.status == "learning", state
    assert state.mastery == 0.5


def test_a_new_session_is_a_new_piece_of_evidence(tmp_path):
    store = _store(tmp_path)
    _answer(store, "排序", True, key="quiz:7:42")
    _answer(store, "排序", True, key="quiz:8:42")

    state = mastery_state(store, "排序")
    assert state.attempts_total == 2
    assert state.status == "mastered"


def test_resubmitting_the_same_question_updates_the_verdict(tmp_path):
    """同一条证据可以被改写（答错后重答），但不会变成两条证据。"""
    store = _store(tmp_path)
    key = "quiz:7:42"
    _answer(store, "栈", False, "incorrect", key=key)
    _answer(store, "栈", True, "correct", key=key)

    state = mastery_state(store, "栈")
    assert state.attempts_total == 1
    assert state.status == "learning"


def test_reanswering_an_old_question_moves_it_to_the_latest_position(tmp_path):
    """重新作答旧题，它应该成为「最近发生的事」，而不是留在时间线旧位置。"""
    store = _store(tmp_path)
    _answer(store, "树", True, "correct", key="quiz:1:1")
    _answer(store, "树", True, "correct", key="quiz:1:2")
    assert mastery_state(store, "树").status == "mastered"

    _answer(store, "树", False, "incorrect", key="quiz:1:1")

    state = mastery_state(store, "树")
    assert state.attempts_total == 2
    assert state.status == "needs_review"


# --- 3. 手动与推断分开 ---

def test_manual_mark_wins_until_new_evidence_arrives(tmp_path):
    store = _store(tmp_path)
    _answer(store, "进程", True)
    ReviewScheduler(store).mark_manual("进程", "mastered")

    manual = mastery_state(store, "进程")
    assert manual.status == "mastered"
    assert manual.status_source == "manual"
    # 掌握度仍然是推导值，不因为用户说"已掌握"就伪造一个 1.0。
    assert manual.mastery == 0.5

    _answer(store, "进程", True)

    after = mastery_state(store, "进程")
    assert after.status_source == "history"
    assert after.status == "mastered"  # 新证据自己也够
    assert after.evidence == 2


def test_manual_mark_alone_has_no_history(tmp_path):
    store = _store(tmp_path)
    ReviewScheduler(store).mark_manual("DP", "needs_review")

    state = mastery_state(store, "DP")
    assert state.status == "needs_review"
    assert state.status_source == "manual"
    assert state.evidence == 0
    assert state.mastery_source == "stored"  # 没有证据，不能说这是算出来的


# --- 4. 旧数据如实降级 ---

def test_legacy_rows_without_history_are_labelled_as_stored(tmp_path):
    store = _store(tmp_path)
    _due(store, "老概念", score=0.7, status="mastered")

    state = mastery_state(store, "老概念")
    assert state.status == "mastered"
    assert state.status_source == "stored"
    assert state.mastery == 0.7
    assert state.mastery_source == "stored"
    assert state.evidence == 0


def test_missing_concepts_are_unseen(tmp_path):
    store = _store(tmp_path)
    state = mastery_state(store, "从没出现过")
    assert state.status == "unseen"
    assert state.status_source == "none"
    assert state.mastery == 0.0


# --- 5. 一个结论：所有入口读同一件事 ---

def test_every_entry_point_agrees_on_the_same_concept(tmp_path):
    from service.learning_service import LearningService

    store = _store(tmp_path)
    _due(store, "极限")
    store.record_mastery_attempt("极限", True, "correct")

    service = LearningService(str(tmp_path))
    progress = service.get_progress(concept="极限")
    due = next(item for item in service.get_due_reviews()["concepts"] if item["concept"] == "极限")
    queue = next(item for item in service.get_review_queue()["due_concepts"] if item["concept"] == "极限")
    overview = mastery_state(store, "极限")

    for payload in (progress, due, queue):
        assert payload["status"] == overview.status == "learning"
        assert payload["mastery"] == overview.mastery == 0.5
        assert payload["evidence"] == overview.evidence == 1


def test_plan_completion_uses_the_derived_status(tmp_path):
    """单次答对不算"学会"，两条证据才算 —— 计划完成判定也必须是这个口径。"""
    store = _store(tmp_path)
    plan_id = store.save_plan(LearningPlan(
        title="两天补齐图论",
        steps=[{"day": 1, "topics": ["图"], "tasks": ["做两题"], "review": []}],
    ))
    tracker = ProgressTracker(store, ReviewScheduler(store))

    tracker.update_from_quiz(["图"], is_correct=True, evidence_key="quiz:1:1")
    assert store.get_plan(plan_id).status == "active"
    assert store.get_plan(plan_id).steps  # 步骤还在，任务未完成

    tracker.update_from_quiz(["图"], is_correct=True, evidence_key="quiz:1:2")
    assert store.get_plan(plan_id).status == "completed"


def test_overview_counts_status_from_derivation(tmp_path):
    store = _store(tmp_path)
    _answer(store, "A", True)
    _answer(store, "B", False, "incorrect")
    _due(store, "C", score=0.9, status="mastered")

    states = {item.concept: item for item in mastery_states(store)}
    assert states["A"].status == "learning"
    assert states["B"].status == "needs_review"
    assert states["C"].status == "mastered"
    # 最弱优先：全错的概念排在最前面。
    assert mastery_states(store)[0].concept == "B"
