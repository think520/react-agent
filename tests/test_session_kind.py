"""W1 E14：会话要有**类别**，练习/复习的辅导会话不能污染主会话列表。

现状：练习辅导用 «bobodan:practice-tutor:<id>» 这样的**普通 chat 会话**在跑，
于是它和真正的聊天一起出现在主会话列表里 —— 用户看到一堆自己没开过的会话。
"""

from __future__ import annotations

import json
from pathlib import Path

from core.session import Session


def _write(save_dir, session: Session) -> None:
    session.save_to_file(str(save_dir / f"{session.session_id}.json"))


def test_session_kind_round_trips(tmp_path):
    session = Session.new(str(tmp_path))
    session.kind = "practice"
    session.session_id = "tutor-1"
    _write(tmp_path, session)

    loaded = Session.load_from_file(str(tmp_path / "tutor-1.json"))

    assert loaded.kind == "practice"


def test_legacy_session_files_count_as_chat(tmp_path):
    """老会话文件没有 kind 字段 —— 不能因此从列表里消失。"""
    legacy = {
        "session_id": "old-1", "cwd": str(tmp_path), "messages": [],
        "created_at": "2026-01-01T00:00:00", "last_active": "2026-01-01T00:00:00",
    }
    (tmp_path / "old-1.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    summaries = Session.list_session_summaries(str(tmp_path))

    assert [item["session_id"] for item in summaries] == ["old-1"]
    assert summaries[0]["kind"] == "chat"


def test_the_main_list_hides_tutor_sessions(tmp_path):
    chat = Session.new(str(tmp_path))
    chat.session_id = "chat-1"
    chat.name = "真的聊天"
    _write(tmp_path, chat)
    tutor = Session.new(str(tmp_path))
    # 注意：文件名里不能有冒号（Windows 非法字符），所以用连字符的 id。
    tutor.session_id = "practice-tutor-3"
    tutor.kind = "practice"
    _write(tmp_path, tutor)

    main = Session.list_session_summaries(str(tmp_path))
    everything = Session.list_session_summaries(str(tmp_path), kind="all")

    assert [item["session_id"] for item in main] == ["chat-1"], main
    assert {item["session_id"] for item in everything} == {"chat-1", "practice-tutor-3"}


def test_loading_an_existing_session_does_not_reclassify_it(tmp_path):
    """已存在的会话保留自己的类别：后续消息（哪怕是另一个入口发的）不能把它改回去。"""
    from web.backend.routers.chat import _load_or_create_session
    from web.backend.deps import get_session_save_dir

    config = {"session": {"max_messages": 40}}
    save_dir = Path(get_session_save_dir(config, str(tmp_path)))
    save_dir.mkdir(parents=True, exist_ok=True)
    tutor = Session.new(str(tmp_path))
    tutor.session_id = "tutor-2"
    tutor.kind = "practice"
    _write(save_dir, tutor)
    assert (save_dir / "tutor-2.json").exists(), list(save_dir.iterdir())

    # 同一条会话被当作"聊天"再打开：类别不变（否则它会突然出现在主列表里）。
    same = _load_or_create_session("tutor-2", config, str(tmp_path), None, kind="chat")
    assert same.kind == "practice"

    # 新建的会话则按调用方声明的类别落库。
    fresh = _load_or_create_session(None, config, str(tmp_path), None, kind="practice")
    assert fresh.kind == "practice"
