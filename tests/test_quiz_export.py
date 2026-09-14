"""E18 / D7: Markdown export of the bank and the backup file format."""

import json

import pytest

from quiz.export import (
    BACKUP_KIND,
    BACKUP_SCHEMA_VERSION,
    bank_backup,
    bank_to_markdown,
    is_third_party,
    restore_bank,
)
from quiz.schema import Question
from quiz.store import QuizStore


def _item(**overrides):
    item = {
        "id": 1,
        "type": "short_answer",
        "question": "Dijkstra 用的是什么策略？",
        "options": [],
        "concepts": ["Dijkstra 算法"],
        "difficulty": "easy",
        "state": "incorrect",
        "answer": "贪心",
        "explanation": "每次取当前最小的未访问顶点",
        "attribution": {"kind": "local_extension", "sources": [{"title": "算法导论"}]},
        "last_attempt": {"user_answer": "动态规划"},
    }
    item.update(overrides)
    return item


def test_markdown_groups_by_state_and_only_shows_known_answers():
    markdown = bank_to_markdown(
        [
            _item(),
            _item(id=2, state="unanswered", answer=None, last_attempt=None, question="BFS 的复杂度？"),
        ],
        generated_at="2026-09-11",
    )

    assert markdown.startswith("---")
    assert "title: 题库导出" in markdown
    assert "## 错题（1）" in markdown
    assert "## 未作答（1）" in markdown
    assert "参考答案：贪心" in markdown
    # The file is read by a person, so it carries the display labels, not keys.
    assert "本地扩展 · 算法导论" in markdown
    assert "你的答案：动态规划" in markdown
    # The unanswered question must not carry an answer into the file.
    assert markdown.count("参考答案") == 1


def test_third_party_questions_are_detected_and_labelled():
    third = _item(attribution={
        "kind": "web",
        "sources": [{"title": "某页练习", "third_party": True}],
    })
    assert is_third_party(third) is True
    assert is_third_party(_item()) is False

    markdown = bank_to_markdown([third], include_third_party=True)
    assert "第三方题目" in markdown
    assert "某页练习" in markdown


def test_backup_round_trip_and_validation(tmp_path):
    store = QuizStore(str(tmp_path))
    qid = store.add_question(Question(question="Q1", answer="A"))
    payload = bank_backup(store)
    assert payload["kind"] == BACKUP_KIND
    assert payload["schema_version"] == BACKUP_SCHEMA_VERSION

    # The JSON round trip is what actually happens over the wire.
    fresh = QuizStore(str(tmp_path / "fresh"))
    counts = restore_bank(fresh, json.loads(json.dumps(payload)))
    assert counts["questions"] == 1
    assert fresh.get_question(qid).question == "Q1"

    for bad in (
        "not a dict",
        {"kind": "something-else"},
        {"kind": BACKUP_KIND, "schema_version": 99, "tables": {}},
        {"kind": BACKUP_KIND, "schema_version": BACKUP_SCHEMA_VERSION},
    ):
        with pytest.raises(ValueError):
            restore_bank(fresh, bad)
