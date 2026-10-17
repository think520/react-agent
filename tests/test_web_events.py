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


def test_a_narration_delta_keeps_its_role():
    """D4：过渡说明与最终答案在传输层就要能区分。"""
    events = to_web_events({"type": "assistant_delta", "content": "我先查一下。", "call_role": "narration"})

    assert events == [("message_delta", {"content": "我先查一下。", "call_role": "narration"})], events


def test_a_plain_delta_is_unchanged():
    """没有角色的增量保持原样（老路径不受影响）。"""
    assert to_web_events({"type": "assistant_delta", "content": "答案。"}) == [
        ("message_delta", {"content": "答案。"})
    ]


# --- 死代码清理（2026-10-17）：practice / learning_update 帧没有生产者，不该再发

def _tool_end_with_artifact(artifact: dict) -> dict:
    return {
        "type": "tool_end",
        "tool_name": "question_generate",
        "ok": True,
        "elapsed": 0.1,
        "artifacts": [artifact],
    }


def test_practice_typed_artifacts_do_not_emit_a_frame():
    # 全仓库没有任何工具会产出 type=practice 的 artifact；以前这里会把它当独立 SSE 帧发出去，
    # 前端也没有消费者 → 死代码。现在必须什么都不发（只剩 status 帧）。
    events = to_web_events(_tool_end_with_artifact({"type": "practice", "artifact_id": "p1"}))

    assert [name for name, _ in events] == ["status"], events


def test_learning_update_typed_artifacts_do_not_emit_a_frame():
    events = to_web_events(_tool_end_with_artifact({"type": "learning_update", "artifact_id": "l1"}))

    assert [name for name, _ in events] == ["status"], events


def test_practice_ready_still_arrives_as_a_chat_artifact():
    # 练习卡走的是这条路（practice_ready → chat_artifact），删掉两个死帧不能碰它。
    events = to_web_events(_tool_end_with_artifact({"type": "practice_ready", "artifact_id": "ready-1"}))

    assert [name for name, _ in events] == ["status", "chat_artifact"], events
    assert events[1][1]["artifact"]["artifact_id"] == "ready-1"


def test_citation_artifact_still_emits_its_own_frame():
    # citation 有真实生产者（rag_search / web_research），必须保留。
    events = to_web_events(_tool_end_with_artifact({"type": "citation", "sources": []}))

    assert [name for name, _ in events] == ["status", "citation"], events

