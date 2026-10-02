"""W1 E4 收尾：**放弃语义** —— 卡片上的「跳过」要同时把暂停的 run 唤醒。

核对现状：卡片只有"回答"一条路；用户不想答时，那一轮就永远停在那里
（只有 7 天数据卫生窗口 + 发下一条消息时才被记为 skipped）。
这里补上：跳过 = 关闭交互（closure=skipped）+ 用"用户跳过了"作为工具结果恢复 run。
超时策略仍未做（如实记账）。
"""

from __future__ import annotations

from service.interaction_service import InteractionService


def test_skip_closes_the_interaction_and_says_so(tmp_path):
    service = InteractionService(str(tmp_path))
    service.register(
        "i1", chat_session_id="c1",
        questions=[{"id": "q1", "prompt": "先学哪个？", "options": ["甲", "乙"]}],
    )
    service.mark_awaiting("i1")
    service.attach_tool_call("i1", "call-1")

    record = service.close("i1", closure="skipped")

    assert record["status"] == "graded", record
    assert record["closure"] == "skipped", record
    assert record["outcome"]["skipped"] is True, record
    # 跳过不是"回答"，所以没有 answered_at。
    assert not record.get("answered_at"), record


def test_the_resume_payload_says_the_user_skipped():
    """恢复 run 时给模型的工具结果必须**如实**说"用户跳过了"，而不是编一个答案。"""
    from web.backend.routers.chat import _resume_content

    content = _resume_content({
        "questions": [{"id": "q1", "prompt": "先学哪个？"}],
        "answers": [],
        "closure": "skipped",
    })

    assert "跳过" in content, content
    assert "未填写" not in content, content


def test_answered_records_still_render_their_answers():
    from web.backend.routers.chat import _resume_content

    content = _resume_content({
        "questions": [{"id": "q1", "prompt": "先学哪个？"}],
        "answers": [{"id": "q1", "answer": "甲"}],
        "closure": "answered",
    })

    assert "甲" in content, content
    assert "跳过" not in content, content


def test_skip_is_idempotent_and_reports_a_missing_interaction(tmp_path):
    service = InteractionService(str(tmp_path))
    service.register("i1", chat_session_id="c1", questions=[{"id": "q1", "prompt": "?"}])
    first = service.close("i1", closure="skipped")
    second = service.close("i1", closure="skipped")

    assert second["closure"] == "skipped", second
    assert first["graded_at"] == second["graded_at"], (first, second)
    assert service.close("nope", closure="skipped") is None
