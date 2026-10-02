"""W1 E11 / D4：流式文本用 «call_role» 区分 narration 与 finish。

核对现状：工具轮的 «response.content»（"我先查一下资料"这类过渡话）**从来没有发给界面** ——
只写进了会话。于是用户看不到模型的过渡说明；而最终的答案正文里也不该混进这些话。
"""

from __future__ import annotations

from core.agent_loop import AgentLoop
from core.session import Session
from providers.types import LLMResponse, LLMStreamChunk, ToolCallDelta


def _session() -> Session:
    return Session.new("/test")


def _fake_execute(calls, history):
    """«_execute_tool_calls» 是生成器（yield 事件、return 状态），stub 要照做。"""
    yield {"type": "tool_start", "tool_name": "rag_search"}
    yield {"type": "tool_end", "tool_name": "rag_search", "ok": True}
    return (False, None)


def test_narration_before_tools_is_emitted_with_its_role(monkeypatch):
    """有工具调用 → 这一轮的文字是 narration（要发出去，但角色不同）。"""
    class _Provider:
        name = "streaming"
        model = "m"

        def __init__(self):
            self.calls = 0

        def complete_stream(self, messages, tools=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield LLMStreamChunk(content_delta="我先查一下资料。")
                yield LLMStreamChunk(
                    tool_call_deltas=[ToolCallDelta(index=0, id="c1", name="rag_search", arguments='{"query": "极限"}')],
                    finish_reason="tool_calls",
                )
            else:
                yield LLMStreamChunk(content_delta="极限的定义是……", finish_reason="stop")

        def complete(self, messages, tools=None, **kwargs):  # pragma: no cover
            raise AssertionError("streaming provider should use complete_stream")

        def get_name(self):
            return "streaming"

    agent = AgentLoop(_Provider(), _session(), tools_schema=[])
    monkeypatch.setattr(agent, "_execute_tool_calls", _fake_execute)

    events = list(agent.run_stream("极限是什么"))

    narration = [event for event in events if event.get("call_role") == "narration"]
    finish = [event for event in events if event.get("call_role") == "finish"]
    assert [event["content"] for event in narration] == ["我先查一下资料。"], events
    assert any("极限的定义是" in event["content"] for event in finish), finish


def test_a_no_tool_answer_is_finish(monkeypatch):
    class _Provider:
        name = "streaming"
        model = "m"

        def complete_stream(self, messages, tools=None, **kwargs):
            yield LLMStreamChunk(content_delta="直接回答。", finish_reason="stop")

        def complete(self, messages, tools=None, **kwargs):  # pragma: no cover
            raise AssertionError("streaming provider should use complete_stream")

        def get_name(self):
            return "streaming"

    events = list(AgentLoop(_Provider(), _session()).run_stream("问题"))

    deltas = [event for event in events if event.get("type") == "assistant_delta"]
    assert deltas and all(event.get("call_role") == "finish" for event in deltas), deltas


def test_a_non_streaming_narration_is_tagged_too(monkeypatch):
    class _Provider:
        name = "plain"
        model = "m"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="我先看看。",
                    tool_calls=[type("TC", (), {"id": "c1", "name": "rag_search", "arguments": "{}",
                                               "to_dict": lambda self: {}})()],
                )
            return LLMResponse(content="答案。")

        def get_name(self):
            return "plain"

    agent = AgentLoop(_Provider(), _session(), tools_schema=[])
    monkeypatch.setattr(agent, "_execute_tool_calls", _fake_execute)

    events = list(agent.run_stream("问题"))

    assert any(event.get("call_role") == "narration" and event.get("content") == "我先看看。" for event in events), events
