"""W1 E11：把新事件接进 Web 适配层。

AgentLoop 现在会发 «assistant_truncated»（被输出上限截断 / 续写中）与
«settlement_started»（探索预算用尽、进入收尾）。核对发现 «to_web_events»
对**未知事件返回空** —— 也就是这两个事件根本到不了界面。
"""

from __future__ import annotations

from web.backend.events import to_web_events


def test_a_truncated_answer_reaches_the_frontend():
    events = to_web_events({
        "type": "assistant_truncated",
        "continuing": False,
        "continues": 2,
    })

    assert events == [("answer_truncated", {"continuing": False, "continues": 2})], events


def test_a_continuing_truncation_is_flagged_as_such():
    events = to_web_events({"type": "assistant_truncated", "continuing": True, "continues": 1})

    assert events[0][0] == "answer_truncated", events
    assert events[0][1]["continuing"] is True, events


def test_settlement_shows_up_as_a_status_line():
    events = to_web_events({"type": "settlement_started", "budget": 2})

    assert events[0][0] == "status", events
    assert "收尾" in events[0][1]["message"], events


def test_unknown_events_still_map_to_nothing():
    """不认识的内部事件不要硬塞给前端（宁可少一个事件，也不要编错语义）。"""
    assert to_web_events({"type": "something_brand_new"}) == []
