from core.session import Session


def test_retry_removes_only_the_failed_turn_and_its_partial_messages(tmp_path):
    session = Session.new(str(tmp_path))
    session.add_message("user", "先前的问题")
    session.add_message("assistant", "先前的回答")
    session.add_message("user", "请解释向量数据库")
    session.add_message_with_tool_calls("assistant", "", [{"id": "call-1"}])
    session.add_tool_message("call-1", "工具失败前的结果")
    session.add_failed_message(
        "assistant",
        "回答没有完成。",
        "回答没有完成。",
        retry_input="请解释向量数据库",
    )

    assert session.remove_failed_turn_for_retry("请解释向量数据库") is True
    assert [message["content"] for message in session.messages] == ["先前的问题", "先前的回答"]


def test_retry_does_not_remove_a_different_user_message(tmp_path):
    session = Session.new(str(tmp_path))
    session.add_message("user", "原问题")
    session.add_failed_message("assistant", "回答没有完成。", "错误", retry_input="原问题")

    assert session.remove_failed_turn_for_retry("另一条问题") is False
    assert len(session.messages) == 2


def test_retry_removes_an_orphaned_failure_marker(tmp_path):
    session = Session.new(str(tmp_path))
    session.add_failed_message("assistant", "回答没有完成。", "错误", retry_input="原问题")

    assert session.remove_failed_turn_for_retry("原问题") is True
    assert session.messages == []

def test_a_failure_without_a_recorded_input_is_not_removed(tmp_path):
    """独立审查（2026-09-30）：没有记下 `retry_input` 的失败标记不能被**无条件**删掉。

    老实现里 `retry_input is None` 会匹配任意失败标记，然后向后找"内容相同"的 user 消息
    并删掉中间整段 —— 任何漏传 retry_input 的调用者都会顺手删掉不相干的一轮。
    现在必须是显式匹配（记不上就什么都不动，重试照常进行）。
    """
    session = Session.new(str(tmp_path))
    session.add_message("user", "另一条问题")
    session.messages.append({"role": "assistant", "content": "失败", "failed": True, "error": "错误"})

    assert session.remove_failed_turn_for_retry("原问题") is False
    assert [message["content"] for message in session.messages] == ["另一条问题", "失败"]
