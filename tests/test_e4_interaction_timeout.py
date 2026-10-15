"""W1 E4 最后一条：**超时策略**（以及顺带发现的一个真 bug）。

核对现状：只有"数据卫生"窗口（7 天，closure=expired）；没有语义化的"等太久就别等了"。
更糟的是 «answer()» 对已经是 graded 的记录**原样返回** —— 于是用户在超时/跳过之后
**迟到的回答会被静默丢弃**（接口 200，答案没了，恢复时用的还是"超时"那个载荷）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from service.interaction_service import (
    DEFAULT_ANSWER_TIMEOUT_HOURS,
    InteractionService,
)


def _register(service: InteractionService, interaction_id: str = "i1") -> dict:
    service.register(
        interaction_id, chat_session_id="c1",
        questions=[{"id": "q1", "prompt": "先学哪个？", "options": ["甲", "乙"], "answer": "甲"}],
    )
    service.mark_awaiting(interaction_id)
    service.attach_tool_call(interaction_id, "call-1")
    return service.get(interaction_id)


def _age(service: InteractionService, interaction_id: str, hours: float) -> None:
    """把创建时间往前挪，模拟"已经等了很久"。"""
    stamp = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    service._update(interaction_id, created_at=stamp)


def test_a_card_that_waited_too_long_times_out(tmp_path):
    service = InteractionService(str(tmp_path), timeout_hours=2)
    _register(service)
    _age(service, "i1", 3)

    swept = service.sweep_timeouts()

    assert swept == 1, swept
    record = service.get("i1")
    assert record["closure"] == "timeout", record
    assert record["status"] == "graded", record
    # 超时不是"作答"，所以没有 answered_at。
    assert not record["answered_at"], record


def test_a_fresh_card_is_left_alone(tmp_path):
    service = InteractionService(str(tmp_path), timeout_hours=48)
    _register(service)
    _age(service, "i1", 1)

    assert service.sweep_timeouts() == 0
    assert service.get("i1")["status"] == "awaiting_input", service.get("i1")


def test_a_late_answer_still_wins_over_the_timeout(tmp_path):
    """用户晚了一天回来认真作答 —— 答案不能被丢掉。"""
    service = InteractionService(str(tmp_path), timeout_hours=2)
    _register(service)
    _age(service, "i1", 3)
    service.sweep_timeouts()
    assert service.get("i1")["closure"] == "timeout"

    record = service.answer("i1", [{"id": "q1", "answer": "甲"}])

    assert record["closure"] == "answered", record
    assert record["answered_at"], record
    assert record["answers"][0]["answer"] == "甲", record
    assert record["outcome"]["correct"] == 1, record


def test_an_answered_record_is_still_idempotent(tmp_path):
    """已经作答过的记录不被二次作答覆盖（幂等保持不变）。"""
    service = InteractionService(str(tmp_path))
    _register(service)
    service.answer("i1", [{"id": "q1", "answer": "甲"}])

    again = service.answer("i1", [{"id": "q1", "answer": "乙"}])

    assert again["answers"][0]["answer"] == "甲", again
    assert again["closure"] == "answered", again


def test_the_timeout_window_is_configurable():
    from core.exploration_budget import CONFIG_SECTION
    from service.interaction_service import resolve_interaction_timeout_hours

    assert resolve_interaction_timeout_hours(None) == DEFAULT_ANSWER_TIMEOUT_HOURS
    assert resolve_interaction_timeout_hours({}) == DEFAULT_ANSWER_TIMEOUT_HOURS
    assert resolve_interaction_timeout_hours({CONFIG_SECTION: {"interaction_timeout_hours": 12}}) == 12
    # 配错了不猜：回到默认。
    for raw in (0, -1, "abc", None):
        assert resolve_interaction_timeout_hours({CONFIG_SECTION: {"interaction_timeout_hours": raw}}) == DEFAULT_ANSWER_TIMEOUT_HOURS, raw


def test_the_resume_payload_is_honest_about_a_timeout():
    from web.backend.routers.chat import _resume_content

    content = _resume_content({
        "questions": [{"id": "q1", "prompt": "先学哪个？"}],
        "answers": [],
        "closure": "timeout",
    })

    assert "时限" in content or "超时" in content, content
    assert "未填写" not in content, content
    assert "跳过" not in content, content


def test_the_resume_payload_is_honest_about_expired_hygiene_rows():
    from web.backend.routers.chat import _resume_content

    content = _resume_content({
        "questions": [{"id": "q1", "prompt": "先学哪个？"}],
        "answers": [],
        "closure": "expired",
    })

    assert "未填写" not in content, content
    assert "过期" in content or "时限" in content or "没有回答" in content, content
