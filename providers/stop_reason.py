"""停止原因的判定（W1 E11）。

不同 provider 的说法不一样（OpenAI 系是 «length»，有的写 «max_tokens»），
所以只做**保守判定**：认识的截断原因才算截断，不认识的当普通结束 ——
宁可漏一次续写，也不要凭猜把一次正常结束变成"再写一遍"。
"""

from __future__ import annotations

#: 各个 provider 用来表示"到了输出上限"的说法。
TRUNCATION_REASONS = frozenset({
    "length",
    "max_tokens",
    "max_output_tokens",
})


def was_truncated(finish_reason: str | None) -> bool:
    """这次输出是不是被**上限**截断的（而不是模型自己写完/要调工具）。"""
    if not finish_reason:
        return False
    return str(finish_reason).strip().casefold() in TRUNCATION_REASONS
