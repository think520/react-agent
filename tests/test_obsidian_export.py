"""Tests for tools.obsidian_export — Obsidian writeback for plans and quiz summaries."""

import json
import os

from learning.store import LearningStore
from learning.schema import LearningPlan
from quiz.store import QuizStore
from quiz.schema import Question, QuizAttempt
from tools.obsidian_export import obsidian_export_plan, obsidian_export_quiz_summary


def _save_plan(ws, title="测试计划", goal="掌握算法", steps=None):
    """Helper: save a learning plan and return it."""
    store = LearningStore(ws)
    if steps is None:
        steps = [
            {"day": 1, "date": "2026-06-10", "topics": ["二叉树", "排序"],
             "materials": ["算法导论.md"], "tasks": ["学习二叉树遍历", "做3道排序题"], "review": ["链表"]},
            {"day": 2, "date": "2026-06-11", "topics": ["图算法"],
             "materials": [], "tasks": ["学习DFS和BFS"], "review": ["二叉树"]},
        ]
    plan = LearningPlan(title=title, goal=goal, steps=steps, course="算法", deadline="2026-06-30")
    plan.id = store.save_plan(plan)
    return plan


def _add_wrong_answers(ws, n=2):
    """Helper: add quiz questions and wrong attempts."""
    qstore = QuizStore(ws)
    qids = []
    for i in range(n):
        qid = qstore.add_question(Question(
            type="single_choice",
            question=f"问题{i+1}",
            options=["A", "B", "C", "D"],
            answer="A",
            explanation=f"解析{i+1}",
            concepts=[f"概念{chr(65+i)}"],
            difficulty="medium",
        ))
        qids.append(qid)
    session = qstore.create_session(qids)
    for qid in qids:
        qstore.record_attempt(QuizAttempt(
            session_id=session.id, question_id=qid,
            user_answer="B", is_correct=False, feedback="错误",
        ))
    return session


# --- obsidian_export_plan tests ---

def test_export_plan_creates_file(tmp_path):
    """Exported plan file exists at the expected path."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    plan = _save_plan(ws)

    result = obsidian_export_plan(plan.id, vault, cwd=ws, workspace=ws)

    assert result.ok is True
    file_path = result.data["file_path"]
    assert os.path.isfile(file_path)
    assert file_path.endswith("测试计划.md")


def test_export_plan_has_frontmatter(tmp_path):
    """Exported markdown has correct YAML frontmatter."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    plan = _save_plan(ws)

    result = obsidian_export_plan(plan.id, vault, cwd=ws, workspace=ws)
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert content.startswith("---")
    assert "title:" in content
    assert "type: learning-plan" in content
    assert "goal:" in content
    assert "deadline:" in content


def test_export_plan_has_checkboxes(tmp_path):
    """Tasks are rendered as markdown checkboxes."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _save_plan(ws)

    plan = LearningStore(ws).get_plan(1)
    result = obsidian_export_plan(plan.id, vault, cwd=ws, workspace=ws)
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert "- [ ] 学习二叉树遍历" in content
    assert "- [ ] 做3道排序题" in content
    assert "- [ ] 学习DFS和BFS" in content


def test_export_plan_has_wikilinks(tmp_path):
    """Concepts are wrapped in [[wikilink]] format."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _save_plan(ws)

    result = obsidian_export_plan(1, vault, cwd=ws, workspace=ws)
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert "[[二叉树]]" in content
    assert "[[排序]]" in content
    assert "[[图算法]]" in content
    assert "[[链表]]" in content


def test_export_plan_concepts_section(tmp_path):
    """Deduplicated concepts appear in the '相关知识点' section."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _save_plan(ws)

    result = obsidian_export_plan(1, vault, cwd=ws, workspace=ws)
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert "## 相关知识点" in content
    # 二叉树 appears in both day 1 topics and day 2 review — should be deduplicated
    assert content.count("[[二叉树]]") >= 2  # once in steps, once in concepts section


def test_export_plan_not_found(tmp_path):
    """Non-existent plan ID returns ok=False."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")

    result = obsidian_export_plan(999, vault, cwd=ws, workspace=ws)

    assert result.ok is False
    assert "not found" in result.content


def test_export_plan_path_outside_workspace(tmp_path):
    """Vault path outside workspace is rejected."""
    ws = str(tmp_path / "workspace")
    os.makedirs(ws)
    vault = str(tmp_path / "other_vault")

    result = obsidian_export_plan(1, vault, cwd=ws, workspace=ws)

    assert result.ok is False
    assert "Access denied" in result.content


def test_export_plan_concepts_in_data(tmp_path):
    """Result data contains unique concepts list."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _save_plan(ws)

    result = obsidian_export_plan(1, vault, cwd=ws, workspace=ws)

    concepts = result.data["concepts"]
    assert "二叉树" in concepts
    assert "排序" in concepts
    assert "图算法" in concepts


# --- obsidian_export_quiz_summary tests ---

def test_export_quiz_summary_creates_file(tmp_path):
    """Exported quiz summary file exists."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _add_wrong_answers(ws)

    result = obsidian_export_quiz_summary(vault, cwd=ws, workspace=ws)

    assert result.ok is True
    assert os.path.isfile(result.data["file_path"])
    assert "做题总结" in result.data["file_path"]


def test_export_quiz_summary_has_frontmatter(tmp_path):
    """Quiz summary has correct frontmatter."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _add_wrong_answers(ws)

    result = obsidian_export_quiz_summary(vault, cwd=ws, workspace=ws)
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert content.startswith("---")
    assert "type: quiz-summary" in content
    assert "date:" in content


def test_export_quiz_summary_wrong_answer_book(tmp_path):
    """Wrong answers are grouped by concept with wikilinks."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _add_wrong_answers(ws, n=2)

    result = obsidian_export_quiz_summary(vault, cwd=ws, workspace=ws)
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert "## 错题本" in content
    assert "[[概念A]]" in content
    assert "[[概念B]]" in content
    assert "问题1" in content
    assert "问题2" in content


def test_export_quiz_summary_weakness_table(tmp_path):
    """Weakness analysis is rendered as a markdown table."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _add_wrong_answers(ws)

    result = obsidian_export_quiz_summary(vault, cwd=ws, workspace=ws)
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert "## 薄弱点分析" in content
    assert "| 知识点 | 做题数 | 错误数 | 错误率 |" in content


def test_export_quiz_summary_mastery_overview(tmp_path):
    """Mastery overview section is present."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    # Create some mastery data first
    from learning.quiz_integration import record_quiz_learning_effect
    record_quiz_learning_effect(ws, ["概念X"], True, "正确")

    result = obsidian_export_quiz_summary(vault, cwd=ws, workspace=ws)
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert "## 掌握度概览" in content
    assert "[[概念X]]" in content
    assert "| 知识点 | 状态 | 分数 |" in content


def test_export_quiz_summary_empty_data(tmp_path):
    """No quiz data still produces a valid file."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")

    result = obsidian_export_quiz_summary(vault, cwd=ws, workspace=ws)

    assert result.ok is True
    with open(result.data["file_path"], encoding="utf-8") as f:
        content = f.read()

    assert "暂无错题记录" in content
    assert "暂无做题记录" in content


def test_export_quiz_summary_path_outside_workspace(tmp_path):
    """Vault path outside workspace is rejected."""
    ws = str(tmp_path / "workspace")
    os.makedirs(ws)
    vault = str(tmp_path / "other_vault")

    result = obsidian_export_quiz_summary(vault, cwd=ws, workspace=ws)

    assert result.ok is False
    assert "Access denied" in result.content


def test_export_quiz_summary_data_counts(tmp_path):
    """Result data contains correct wrong_count and weakness_count."""
    ws = str(tmp_path)
    vault = str(tmp_path / "vault")
    _add_wrong_answers(ws, n=3)

    result = obsidian_export_quiz_summary(vault, cwd=ws, workspace=ws)

    assert result.data["wrong_count"] == 3
    assert result.data["weakness_count"] >= 1
