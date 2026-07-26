import json
import os
import sqlite3

from learning.schema import Mastery, LearningPlan
from learning.store import LearningStore
from learning.scheduler import ReviewScheduler
from learning.progress import ProgressTracker
from learning.path import LearningPathGenerator


# --- Schema tests ---

def test_mastery_defaults():
    m = Mastery(concept="Dijkstra")
    assert m.concept == "Dijkstra"
    assert m.status == "unseen"
    assert m.score == 0.0
    assert m.review_count == 0
    assert m.consecutive_correct == 0
    assert m.ease_factor == 2.5
    assert m.interval_days == 0
    assert m.source == "auto"


def test_learning_plan_defaults():
    p = LearningPlan()
    assert p.steps == []
    assert p.id is None


# --- Store tests ---

def test_store_creates_tables(tmp_path):
    store = LearningStore(str(tmp_path))
    assert os.path.exists(store.db_path)


def test_store_migrates_sm2_columns_from_legacy_mastery_table(tmp_path):
    knowledge_dir = tmp_path / ".knowledge"
    knowledge_dir.mkdir()
    db_path = knowledge_dir / "bobodan.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE mastery (
        concept TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'unseen',
        score REAL NOT NULL DEFAULT 0.0, review_count INTEGER NOT NULL DEFAULT 0,
        consecutive_correct INTEGER NOT NULL DEFAULT 0, last_reviewed TEXT,
        next_review TEXT, source TEXT NOT NULL DEFAULT 'auto', updated_at TEXT NOT NULL
    )""")
    conn.execute("""INSERT INTO mastery (
        concept, status, score, review_count, consecutive_correct, source, updated_at
    ) VALUES ('图', 'learning', 0.2, 1, 1, 'auto', '2026-01-01T00:00:00+00:00')""")
    conn.commit()
    conn.close()

    store = LearningStore(str(tmp_path))
    mastery = store.get_mastery("图")

    assert mastery is not None
    assert mastery.ease_factor == 2.5
    assert mastery.interval_days == 0


def test_upsert_and_get_mastery(tmp_path):
    store = LearningStore(str(tmp_path))
    m = Mastery(concept="贪心算法", status="learning", score=0.5)
    store.upsert_mastery(m)

    loaded = store.get_mastery("贪心算法")
    assert loaded is not None
    assert loaded.concept == "贪心算法"
    assert loaded.status == "learning"
    assert loaded.score == 0.5


def test_upsert_updates_existing(tmp_path):
    store = LearningStore(str(tmp_path))
    store.upsert_mastery(Mastery(concept="排序", score=0.3))
    store.upsert_mastery(Mastery(concept="排序", score=0.8))

    loaded = store.get_mastery("排序")
    assert loaded.score == 0.8


def test_list_mastery(tmp_path):
    store = LearningStore(str(tmp_path))
    store.upsert_mastery(Mastery(concept="A", status="learning"))
    store.upsert_mastery(Mastery(concept="B", status="mastered"))
    store.upsert_mastery(Mastery(concept="C", status="needs_review"))

    all_m = store.list_mastery()
    assert len(all_m) == 3

    learning = store.list_mastery(status="learning")
    assert len(learning) == 1
    assert learning[0].concept == "A"


def test_count_by_status(tmp_path):
    store = LearningStore(str(tmp_path))
    store.upsert_mastery(Mastery(concept="A", status="learning"))
    store.upsert_mastery(Mastery(concept="B", status="learning"))
    store.upsert_mastery(Mastery(concept="C", status="mastered"))

    counts = store.count_by_status()
    assert counts["learning"] == 2
    assert counts["mastered"] == 1


def test_save_and_get_plan(tmp_path):
    store = LearningStore(str(tmp_path))
    plan = LearningPlan(
        title="操作系统复习",
        goal="期末考试",
        steps=[{"day": 1, "topics": ["进程"], "tasks": ["读书"]}],
        course="操作系统",
    )
    plan_id = store.save_plan(plan)
    assert plan_id > 0

    loaded = store.get_plan(plan_id)
    assert loaded is not None
    assert loaded.title == "操作系统复习"
    assert loaded.steps[0]["topics"] == ["进程"]


def test_list_plans(tmp_path):
    store = LearningStore(str(tmp_path))
    store.save_plan(LearningPlan(title="Plan A"))
    store.save_plan(LearningPlan(title="Plan B"))

    plans = store.list_plans()
    assert len(plans) == 2


# --- Scheduler tests ---

def test_scheduler_record_correct(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    m = scheduler.record_review("二叉树", correct=True)
    assert m.status == "learning"
    assert m.consecutive_correct == 1
    assert m.score > 0
    assert m.next_review is not None
    assert m.interval_days == 1


def test_scheduler_two_correct_makes_mastered(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    scheduler.record_review("堆", correct=True)
    m = scheduler.record_review("堆", correct=True)
    assert m.status == "mastered"
    assert m.consecutive_correct == 2
    assert m.interval_days == 6
    assert m.score >= 0.3


def test_scheduler_wrong_resets_consecutive(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    scheduler.record_review("图", correct=True)
    m = scheduler.record_review("图", correct=False)
    assert m.consecutive_correct == 0
    assert m.status == "needs_review"
    assert m.interval_days == 1
    assert m.ease_factor < 2.5
    assert m.score < 0.5


def test_scheduler_wrong_decreases_score(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    m = scheduler.record_review("哈希", correct=False)
    assert m.score == 0.0  # can't go below 0


def test_scheduler_get_due_concepts(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    # Record a wrong answer (next_review = tomorrow)
    scheduler.record_review("链表", correct=False)
    due = scheduler.get_due_concepts()
    # Not due yet (tomorrow)
    assert len(due) == 0


def test_scheduler_mark_manual(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)

    m = scheduler.mark_manual("DP", "mastered")
    assert m.status == "mastered"
    assert m.source == "manual"
    assert m.score >= 0.8


# --- Progress tests ---

def test_progress_overview_empty(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)

    overview = progress.get_overview()
    assert overview["total_concepts"] == 0


def test_progress_overview_with_data(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)

    scheduler.record_review("A", correct=True)
    scheduler.record_review("B", correct=False)

    overview = progress.get_overview()
    assert overview["total_concepts"] == 2
    assert "learning" in overview["by_status"] or "needs_review" in overview["by_status"]


def test_progress_update_from_quiz(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)

    results = progress.update_from_quiz(["概念X", "概念Y"], is_correct=True)
    assert len(results) == 2
    assert all(m.score > 0 for m in results)


def test_progress_concept_detail(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)

    scheduler.record_review("排序算法", correct=True)
    detail = progress.get_concept_detail("排序算法")
    assert detail is not None
    assert detail["concept"] == "排序算法"
    assert detail["status"] == "learning"


def test_progress_concept_detail_not_found(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)

    assert progress.get_concept_detail("不存在") is None


# --- Path generator tests ---

def test_path_generator_simple_plan(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)
    generator = LearningPathGenerator(store, progress, llm_provider=None)

    plan = generator.generate_path(goal="复习数据结构")
    assert plan.title != ""
    assert len(plan.steps) >= 1
    assert plan.id is not None


def test_path_generator_with_weakness(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)

    # Create some weakness data
    scheduler.record_review("二叉树", correct=False)
    scheduler.record_review("图", correct=False)

    generator = LearningPathGenerator(store, progress, llm_provider=None)
    plan = generator.generate_path(goal="补薄弱点")
    assert len(plan.steps) >= 1


def test_path_generator_reads_course_info_from_sqlite_index(tmp_path):
    import json

    from rag.sqlite_store import KBSQLiteStore

    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)
    kb = KBSQLiteStore(str(tmp_path))
    kb.init_db()
    kb.upsert_document(
        "doc-a", "course/lesson-a.md", "hash-a", title="Lesson A", course="CS101",
    )
    kb.upsert_document(
        "doc-b", "course/lesson-b.md", "hash-b", title="Lesson B", course="CS102",
    )
    kb.close()
    (tmp_path / ".knowledge" / "rag_index.json").write_text(
        json.dumps({"chunks": [{"source": "legacy/should-not-appear.md"}]}),
        encoding="utf-8",
    )

    generator = LearningPathGenerator(store, progress, llm_provider=None)
    summary = generator._get_course_info(str(tmp_path), course="CS101")

    assert "course/lesson-a.md" in summary
    assert "course/lesson-b.md" not in summary
    assert "legacy/should-not-appear.md" not in summary


def test_path_generator_does_not_create_empty_index(tmp_path):
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)
    generator = LearningPathGenerator(store, progress, llm_provider=None)

    assert generator._get_course_info(str(tmp_path)) == ""
    assert not (tmp_path / ".knowledge" / "knowledge.db").exists()


def test_parse_plan_json():
    from learning.path import LearningPathGenerator

    raw = '{"title": "Test", "steps": [{"day": 1, "topics": ["A"]}]}'
    result = LearningPathGenerator._parse_plan_json(raw)
    assert result["title"] == "Test"
    assert len(result["steps"]) == 1


def test_parse_plan_json_markdown_fenced():
    from learning.path import LearningPathGenerator

    raw = '```json\n{"title": "Plan", "steps": []}\n```'
    result = LearningPathGenerator._parse_plan_json(raw)
    assert result["title"] == "Plan"


def test_parse_plan_json_invalid():
    from learning.path import LearningPathGenerator

    assert LearningPathGenerator._parse_plan_json("no json") == {}


# --- Tool integration tests ---

def test_learning_progress_tool_no_data(tmp_path):
    from tools.learning_tools import learning_progress
    result = learning_progress(workspace=str(tmp_path))
    assert result.ok
    assert "暂无" in result.content


def test_learning_review_tool_no_data(tmp_path):
    from tools.learning_tools import learning_review
    result = learning_review(workspace=str(tmp_path))
    assert result.ok
    assert "没有" in result.content


def test_learning_path_tool_no_llm(tmp_path):
    from learning.path import LearningPathGenerator
    store = LearningStore(str(tmp_path))
    scheduler = ReviewScheduler(store)
    progress = ProgressTracker(store, scheduler)
    generator = LearningPathGenerator(store, progress, llm_provider=None)
    plan = generator.generate_path(goal="测试目标", workspace=str(tmp_path))
    assert plan.id is not None
    assert len(plan.steps) >= 1
