"""Unit tests for core.session_compactor (AG-3.3)."""

from core.session_compactor import (
    CHECKPOINT_MARKER,
    Checkpoint,
    estimate_messages_tokens,
    estimate_tokens,
    project_context,
    should_compact,
)


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1


def test_should_compact_when_over_reserve():
    big = [{"role": "user", "content": "x" * 40000}]
    assert should_compact(big, context_window=12000, output_reserve=4000) is True


def test_should_compact_false_when_under_reserve():
    small = [{"role": "user", "content": "hello"}]
    assert should_compact(small, context_window=12000, output_reserve=4000) is False


def test_checkpoint_from_summary_parses_fields():
    summary = "目标: 复习线性代数\n进展: 已学矩阵\n阻塞: 无\n下一步: 做特征值练习"
    cp = Checkpoint.from_summary(summary)
    assert cp.goal == "复习线性代数"
    assert cp.progress == "已学矩阵"
    assert cp.blockers == "无"
    assert cp.next_steps == "做特征值练习"


def test_checkpoint_from_summary_falls_back_to_summary_field():
    cp = Checkpoint.from_summary("非结构化摘要")
    assert cp.summary == "非结构化摘要"
    assert not cp.goal


def test_checkpoint_merge_is_incremental():
    old = Checkpoint(goal="学微积分", progress="已学极限", blockers="", next_steps="学导数")
    new = Checkpoint(goal="", progress="已学导数", blockers="卡在积分", next_steps="做积分题")
    merged = old.merge(new)
    assert merged.goal == "学微积分"
    assert merged.progress == "已学极限；已学导数"
    assert merged.blockers == "卡在积分"
    assert merged.next_steps == "做积分题"


def test_checkpoint_to_message_has_marker():
    cp = Checkpoint(goal="g", progress="p")
    message = cp.to_message()
    assert message["role"] == "system"
    assert CHECKPOINT_MARKER in message["content"]
    assert "目标: g" in message["content"]


def test_project_context_preserves_system_prefix_and_tail(tmp_path):
    messages = [
        {"role": "system", "content": "identity"},
        {"role": "system", "content": "evidence contract"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
    ]
    cp = Checkpoint(goal="goal")
    projected = project_context(messages, cp, tail=2)

    roles = [m["role"] for m in projected]
    assert roles[0:2] == ["system", "system"]
    assert projected[2]["content"].startswith(CHECKPOINT_MARKER)
    # Tail keeps only the most recent 2 non-system messages.
    assert roles[-2:] == ["assistant", "user"]


def test_project_context_does_not_mutate_input():
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    project_context(messages, None)
    assert messages == [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_estimate_messages_tokens_sums_content():
    messages = [{"role": "user", "content": "abcd"}, {"role": "assistant", "content": "efgh"}]
    assert estimate_messages_tokens(messages) == 2
