"""划线锚点的重锚定（W1 E7）。

锚点是**四元组 + 引文**：«document_id + chunk_id + char_start/char_end + quote»。
偏移会随分段重切或资料被编辑而失效，所以判定顺序是：

1. 偏移仍然对得上引文 → «exact»（原样可用）；
2. 否则在当前分段里**按引文找回** → «relocated»（如实说"位置变了"，并给出新偏移）；
3. 找不到 → «stale»（**不猜**：宁可告诉用户这条划线需要重新指认）。

跨分段找回（引文跑到别的 chunk 里）本轮未做 —— 那需要一次全库定位，属于下一步。
"""

from __future__ import annotations

from typing import Any

ANCHOR_EXACT = "exact"
ANCHOR_RELOCATED = "relocated"
ANCHOR_STALE = "stale"


def resolve_anchor(anchor: dict[str, Any], chunk_text: str) -> dict[str, Any]:
    """把一条锚点落到**当前**分段文本上。"""
    quote = str(anchor.get("quote") or "")
    text = chunk_text or ""
    start = anchor.get("char_start")
    end = anchor.get("char_end")

    if not quote:
        return {"status": ANCHOR_STALE, "char_start": None, "char_end": None}

    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text):
        if text[start:end] == quote:
            return {"status": ANCHOR_EXACT, "char_start": start, "char_end": end}

    found = text.find(quote)
    if found >= 0:
        return {"status": ANCHOR_RELOCATED, "char_start": found, "char_end": found + len(quote)}

    return {"status": ANCHOR_STALE, "char_start": None, "char_end": None}
