import time
from core.session import Session


def test_session_new():
    session = Session.new("/test/path", max_messages=5)
    assert session.session_id is not None
    assert session.cwd == "/test/path"
    assert session.max_messages == 5
    assert len(session.messages) == 0


def test_session_add_message():
    session = Session.new("/test/path")
    session.add_message("user", "hello")
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hello"


def test_session_add_tool_message_updates_last_active():
    session = Session.new("/test/path")
    session.last_active = "old"

    session.add_tool_message("call_1", "tool output")

    assert session.messages[0]["role"] == "tool"
    assert session.messages[0]["tool_call_id"] == "call_1"
    assert session.last_active != "old"


def test_session_max_messages_trim():
    session = Session.new("/test/path", max_messages=2)
    session.add_message("user", "one")
    session.add_message("assistant", "two")
    session.add_message("user", "three")

    assert len(session.messages) == 2
    assert session.messages[0]["content"] == "two"
    assert session.messages[1]["content"] == "three"


def test_session_save_load(tmp_path):
    session = Session.new(str(tmp_path), max_messages=3)
    session.add_message("user", "test")

    save_path = tmp_path / "test_session.json"
    session.save_to_file(str(save_path))

    loaded = Session.load_from_file(str(save_path))
    assert loaded.session_id == session.session_id
    assert loaded.messages[0]["content"] == "test"
    assert loaded.max_messages == 3


def test_list_sessions_returns_ids(tmp_path):
    (tmp_path / "abc.json").write_text("{}", encoding="utf-8")
    (tmp_path / "def.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")

    sessions = Session.list_sessions(str(tmp_path))

    assert sessions == ["abc", "def"]


def test_session_trim_preserves_system_message():
    session = Session.new("/test/path", max_messages=3)
    session.add_message("system", "You are a helpful assistant.")
    session.add_message("user", "one")
    session.add_message("assistant", "two")
    session.add_message("user", "three")  # triggers trim

    assert len(session.messages) == 3
    assert session.messages[0]["role"] == "system"
    assert session.messages[0]["content"] == "You are a helpful assistant."
    assert session.messages[1]["content"] == "two"
    assert session.messages[2]["content"] == "three"


def test_session_workspace_root_set_on_new():
    session = Session.new("/test/path")
    assert session.workspace_root == "/test/path"
    assert session.cwd == "/test/path"


def test_session_workspace_root_persists_on_save_load(tmp_path):
    session = Session.new(str(tmp_path))
    save_path = tmp_path / "ws_test.json"
    session.save_to_file(str(save_path))

    loaded = Session.load_from_file(str(save_path))
    assert loaded.workspace_root == str(tmp_path)
    assert loaded.cwd == str(tmp_path)


def test_session_load_old_format_without_workspace_root(tmp_path):
    """Old sessions without workspace_root field should default to cwd."""
    import json
    data = {
        "session_id": "old-session",
        "cwd": "/old/path",
        "messages": [],
        "created_at": "2026-01-01T00:00:00",
        "last_active": "2026-01-01T00:00:00",
        "max_messages": None,
    }
    save_path = tmp_path / "old_session.json"
    with open(save_path, "w") as f:
        json.dump(data, f)

    loaded = Session.load_from_file(str(save_path))
    assert loaded.workspace_root == "/old/path"


def test_session_name_field(tmp_path):
    session = Session.new(str(tmp_path))
    session.name = "正则表达式练习"
    save_path = tmp_path / "named.json"
    session.save_to_file(str(save_path))

    loaded = Session.load_from_file(str(save_path))
    assert loaded.name == "正则表达式练习"


def test_session_name_defaults_empty_for_old_format(tmp_path):
    """Old sessions without name field should default to empty string."""
    import json
    data = {
        "session_id": "old-session",
        "cwd": "/old/path",
        "messages": [],
        "created_at": "2026-01-01T00:00:00",
        "last_active": "2026-01-01T00:00:00",
        "max_messages": None,
    }
    save_path = tmp_path / "old.json"
    with open(save_path, "w") as f:
        json.dump(data, f)

    loaded = Session.load_from_file(str(save_path))
    assert loaded.name == ""


def test_list_session_summaries(tmp_path):
    import json
    # Create two sessions
    s1 = Session.new(str(tmp_path))
    s1.name = "session A"
    s1.add_message("user", "hello")
    s1.save_to_file(str(tmp_path / f"{s1.session_id}.json"))

    s2 = Session.new(str(tmp_path))
    s2.name = "session B"
    s2.add_message("user", "hi")
    s2.add_message("assistant", "hey")
    s2.save_to_file(str(tmp_path / f"{s2.session_id}.json"))

    summaries = Session.list_session_summaries(str(tmp_path))
    assert len(summaries) == 2
    # Sorted by last_active descending
    names = [s["name"] for s in summaries]
    assert "session A" in names
    assert "session B" in names
    # Check message count
    for s in summaries:
        if s["name"] == "session A":
            assert s["message_count"] == 1
        elif s["name"] == "session B":
            assert s["message_count"] == 2


def test_list_session_summaries_empty(tmp_path):
    assert Session.list_session_summaries(str(tmp_path)) == []
