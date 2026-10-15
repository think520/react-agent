"""W2 G3：索引心跳守卫 —— 向量索引"没有进度"时要报**可行动**的错误。

核对现状：«rag/» 里**没有任何心跳/无进度守卫**；单次请求虽然有 10s 传输超时，
但"很多批都很慢/一直重试"仍会表现为**整体没有进度**（路线图说的本地 embedding
黑洞连接正是这种形态）。
"""

from __future__ import annotations

import pytest

from rag.index_guard import (
    DEFAULT_STALL_SECONDS,
    IndexStalledError,
    StallGuard,
    resolve_stall_seconds,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_progress_resets_the_clock():
    clock = Clock()
    guard = StallGuard(timeout_seconds=600, clock=clock)

    clock.advance(500)
    guard.beat()
    clock.advance(500)

    assert guard.stalled() is False
    guard.ensure_progress()  # 不抛


def test_a_long_silence_is_a_stall_with_an_actionable_message():
    clock = Clock()
    guard = StallGuard(timeout_seconds=600, clock=clock)
    clock.advance(601)

    assert guard.stalled() is True
    with pytest.raises(IndexStalledError) as excinfo:
        guard.ensure_progress()

    message = str(excinfo.value)
    assert "秒没有进度" in message, message
    assert "embedding" in message, message
    # 要告诉用户"没丢东西、下次还会重试"，否则这条错误不可行动。
    assert "pending" in message, message
    assert "重试" in message, message


def test_the_boundary_counts_as_stalled():
    clock = Clock()
    guard = StallGuard(timeout_seconds=600, clock=clock)
    clock.advance(600)

    assert guard.stalled() is True


def test_the_guard_remembers_why_it_stopped():
    clock = Clock()
    guard = StallGuard(timeout_seconds=10, clock=clock)
    clock.advance(11)

    with pytest.raises(IndexStalledError):
        guard.ensure_progress()

    # 汇总/日志要能直接引用，不用再拼一次。
    assert guard.stall_message
    assert "秒没有进度" in guard.stall_message


def test_the_threshold_is_configurable_and_never_guessed():
    assert resolve_stall_seconds(None) == DEFAULT_STALL_SECONDS
    assert resolve_stall_seconds({}) == DEFAULT_STALL_SECONDS
    assert resolve_stall_seconds({"rag": {"index_stall_seconds": 30}}) == 30
    for raw in (0, -5, "abc", None, []):
        assert resolve_stall_seconds({"rag": {"index_stall_seconds": raw}}) == DEFAULT_STALL_SECONDS, raw
    assert resolve_stall_seconds({"rag": "not-a-dict"}) == DEFAULT_STALL_SECONDS
