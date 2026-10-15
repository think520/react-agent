"""W2 G3：索引心跳守卫 —— 向量索引**没有进度**时报可行动的错误，而不是一直等下去。

为什么需要它：单次 embedding 请求已经有传输超时（默认 10s）与有界重试，所以「卡死」
通常不是一次请求永远不返回，而是**整体没有进度** —— 本地 embedding 服务连上了却不回
数据（黑洞连接），或者每批都在超时重试。用户看到的只是「索引卡住了」，没有任何解释。

设计取舍：
- 守卫**只报进度**，不猜原因、不杀线程；调用方决定怎么处理（保留已完成、剩下的留 pending）。
- 时钟可注入 → 纯函数可测，不需要真的等 600 秒。
- 阈值可配（`rag.index_stall_seconds`）；配得不合理就回到默认 600s，不猜。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

#: 默认阈值：600 秒没有任何进度就算卡住（路线图 G3 的原始要求）。
DEFAULT_STALL_SECONDS = 600


class IndexStalledError(RuntimeError):
    """索引超过时限没有进度。消息本身要能指导下一步动作。"""


def stall_message(elapsed_seconds: float, timeout_seconds: float = DEFAULT_STALL_SECONDS) -> str:
    """可行动的错误文案：说清多久没进度、为什么、东西没丢、下一步做什么。"""
    return (
        f"向量索引已 {int(elapsed_seconds)} 秒没有进度（阈值 {int(timeout_seconds)} 秒）。"
        "常见原因是 embedding 服务连上了却不回数据（本地 Ollama 黑洞连接），"
        "或每批都在超时重试。"
        "已经完成的资料保持 indexed；没做完的仍是 pending，下次同步会自动重试（不用重来）。"
        "可以检查 embedding 服务是否在跑 / 换一个 provider（设置 → 模型），"
        "或者调大 rag.index_stall_seconds。"
    )


@dataclass
class StallGuard:
    """记录「上一次真实进度」的时刻；太久没有进度就判定卡住。"""

    timeout_seconds: float = DEFAULT_STALL_SECONDS
    clock: Callable[[], float] = time.monotonic
    last_progress: float = field(default=0.0)
    #: 卡住时的可行动说明（调用方直接拿去汇总/上屏，不用再拼一次）。
    stall_message: str = ""

    def __post_init__(self) -> None:
        if not self.last_progress:
            self.last_progress = self.clock()

    def beat(self) -> None:
        """报告一次真实进度（例如一份资料的向量已经落进 Qdrant）。"""
        self.last_progress = self.clock()

    def elapsed(self) -> float:
        return max(0.0, self.clock() - self.last_progress)

    def stalled(self) -> bool:
        return self.elapsed() >= float(self.timeout_seconds)

    def ensure_progress(self) -> None:
        """没进度就抛 `IndexStalledError`（并把说明记在 `stall_message` 上）。"""
        if not self.stalled():
            return
        self.stall_message = stall_message(self.elapsed(), self.timeout_seconds)
        raise IndexStalledError(self.stall_message)


def resolve_stall_seconds(config: dict[str, Any] | None = None) -> float:
    """`rag.index_stall_seconds`；没配或配得不合理就用默认值，不猜。"""
    section = (config or {}).get("rag") or {}
    if not isinstance(section, dict):
        return float(DEFAULT_STALL_SECONDS)
    raw = section.get("index_stall_seconds")
    if raw is None:
        return float(DEFAULT_STALL_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(DEFAULT_STALL_SECONDS)
    return value if value > 0 else float(DEFAULT_STALL_SECONDS)