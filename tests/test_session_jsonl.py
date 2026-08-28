"""Tests for the AG-1 conditional JSONL session migration (core/session_jsonl.py)."""

import json
import os

from core.session import Session
from core.session_jsonl import (
    ENTRY_MESSAGE,
    ENTRY_SESSION,
    migrate_json_to_jsonl,
    session_from_jsonl,
    session_to_jsonl,
)


def _make_session(tmp_path):
    session = Session.new(str(tmp_path), max_messages=20)
    session.name = "测试会话"
    session.library_id = "lib-1"
    session.provider_name = "deepseek"
    session.add_message("user", "hello")
    session.add_message("assistant", "hi there")
    session.add_message_with_tool_calls("assistant", "", [{"id": "c1", "function": {"name": "rag_search", "arguments": "{}"}}])
    session.add_tool_message("c1", "result")
    return session


def test_round_trip_preserves_session(tmp_path):
    session = _make_session(tmp_path)
    text = session_to_jsonl(session)

    lines = [line for line in text.splitlines() if line.strip()]
    assert json.loads(lines[0])["type"] == ENTRY_SESSION

    restored = session_from_jsonl(text)
    assert restored.session_id == session.session_id
    assert restored.name == "测试会话"
    assert restored.library_id == "lib-1"
    assert restored.provider_name == "deepseek"
    assert restored.messages == session.messages


def test_jsonl_messages_are_linear_with_parent_id(tmp_path):
    session = _make_session(tmp_path)
    text = session_to_jsonl(session)

    message_entries = [json.loads(line) for line in text.splitlines()
                       if line.strip() and json.loads(line)["type"] == ENTRY_MESSAGE]
    assert message_entries
    for entry in message_entries:
        assert entry["parentId"] == session.session_id


def test_migrate_json_to_jsonl_archives_original(tmp_path):
    session = _make_session(tmp_path)
    json_path = os.path.join(str(tmp_path), f"{session.session_id}.json")
    session.save_to_file(json_path)

    result = migrate_json_to_jsonl(json_path)

    assert result["ok"] is True
    assert os.path.isfile(result["jsonl_path"])
    assert not os.path.isfile(json_path)  # archived
    assert os.path.isfile(json_path + ".archived")

    # The migrated JSONL can be read back losslessly.
    with open(result["jsonl_path"], "r", encoding="utf-8") as handle:
        restored = session_from_jsonl(handle.read())
    assert restored.session_id == session.session_id
    assert len(restored.messages) == len(session.messages)


def test_migrate_missing_file_fails_cleanly(tmp_path):
    result = migrate_json_to_jsonl(os.path.join(str(tmp_path), "nope.json"))
    assert result["ok"] is False
    assert result["code"] == "not_found"


def test_migrate_invalid_json_does_not_delete(tmp_path):
    bad = os.path.join(str(tmp_path), "bad.json")
    with open(bad, "w", encoding="utf-8") as handle:
        handle.write("{not json")

    result = migrate_json_to_jsonl(bad)
    assert result["ok"] is False
    assert result["code"] in {"invalid_session", "validation_failed"}
    # Original is untouched.
    assert os.path.isfile(bad)
