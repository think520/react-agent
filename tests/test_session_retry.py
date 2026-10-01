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
