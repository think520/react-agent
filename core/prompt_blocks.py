"""Named prompt blocks (W1 E12).

设计来自参考项目（docs/Bobodan参考项目调研报告.md 的 D5/D13，对应
`deeptutor/agents/chat/prompt_blocks.py` 与 `agentic_pipeline.py` L1282-1320）：

- system 侧拆成**具名块**，每块有 marker、顺序固定、内容**逐字节稳定** —— 同一轮里重复组装
  不会产生 diff，对缓存也友好（`core/agent_loop.py` 已经用 marker 做幂等注入）。
- 进循环前先检索一次，把命中拼成 `[Knowledge Base Context]` 追加到**末尾 user 消息**，
  并明示"不完整、可以继续检索" —— 预检索只解决冷启动，**不替代**工具检索。
"""

from __future__ import annotations

from typing import Any, Iterable

KB_CONTEXT_HEADER = "[Knowledge Base Context]"

KB_SEED_NOTE = (
    "以上是进入本轮前自动预检索到的片段，**可能不完整**；"
    "需要更多证据时继续用 rag_search 检索，并以检索结果为准。"
)

DEFAULT_MAX_CHARS = 4000


def _hit_sort_key(hit: dict[str, Any]) -> tuple[str, str]:
    return (str(hit.get("document_id") or ""), str(hit.get("chunk_id") or ""))


def _hit_line(hit: dict[str, Any]) -> str:
    from rag.citations import cite_label, hit_source_id

    chunk_id = str(hit.get("chunk_id") or "").strip()
    title = str(hit.get("title") or hit.get("document_id") or "").strip()
    text = " ".join(str(hit.get("text") or "").split())
    label = f"{title} · {chunk_id}" if chunk_id else title
    # W2-EVID-01：与 rag_search 结果同一套标签，模型引用预检索片段也能被核对。
    source_id = hit_source_id(hit)
    if source_id:
        label = f"[{cite_label(source_id)}] {label}".rstrip()
    return f"- {label}：{text}" if label else f"- {text}"


def build_kb_seed_block(
    hits: Iterable[dict[str, Any]],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """把预检索命中拼成具名块。没有命中就返回空串（不注入空块）。

    排序固定（document_id, chunk_id），所以同一批命中不管检索返回什么顺序，
    结果**逐字节相同**。
    """
    ordered = sorted((hit for hit in hits if isinstance(hit, dict)), key=_hit_sort_key)
    if not ordered:
        return ""

    budget = max(200, int(max_chars))
    used: list[str] = []
    length = 0
    dropped = 0
    for hit in ordered:
        line = _hit_line(hit)
        if not line.strip():
            continue
        remaining = budget - length
        if remaining <= 40:
            dropped += 1
            continue
        if len(line) + 1 > remaining:
            # 单条超长就**截断**（否则一条长 chunk 会独自撑爆预算）。
            line = line[: remaining - 12].rstrip() + " …（截断）"
        used.append(line)
        length += len(line) + 1

    if not used:
        return ""

    lines = [KB_CONTEXT_HEADER, *used]
    if dropped:
        lines.append(f"（还有 {dropped} 条命中未列出，需要时请自行检索。）")
    lines.append(KB_SEED_NOTE)
    from rag.citations import CITATION_INSTRUCTION

    lines.append(CITATION_INSTRUCTION)
    return "\n".join(lines)


def attach_kb_seed(message: str, block: str) -> str:
    """把块追加到消息末尾；已经有块（重试、多轮再注入）就原样返回。"""
    if not block:
        return message
    if KB_CONTEXT_HEADER in message:
        return message
    separator = "\n\n" if message and not message.endswith("\n") else ""
    return f"{message}{separator}{block}"


CONCEPT_MAP_CONTEXT_HEADER = "[Reviewed Concept Map Context]"

CONCEPT_MAP_SEED_NOTE = (
    "以上是用户已审查知识地图中的概念结构，仅用于理清前置依赖、组成与对比关系；"
    "不可替代原文证据，具体事实与引用仍须以 rag_search 原文片段为准。"
)


def build_concept_map_seed_block(
    context: dict[str, Any],
    *,
    max_chars: int = 1600,
) -> str:
    """Format matched reviewed concepts and 1-hop relationships without citation tags."""
    if not isinstance(context, dict):
        return ""
    concepts = [c for c in (context.get("concepts") or []) if isinstance(c, dict)]
    relationships = [r for r in (context.get("relationships") or []) if isinstance(r, dict)]
    if not concepts:
        return ""

    ordered_concepts = sorted(concepts, key=lambda c: str(c.get("concept_id") or ""))
    ordered_rels = sorted(
        relationships,
        key=lambda r: (0 if r.get("rel_type") == "前置知识" else 1, str(r.get("rel_id") or "")),
    )

    budget = max(240, int(max_chars))
    body: list[str] = []
    used_len = len(CONCEPT_MAP_CONTEXT_HEADER) + len(CONCEPT_MAP_SEED_NOTE) + 4

    for concept in ordered_concepts:
        name = str(concept.get("name") or "").strip()
        if not name:
            continue
        definition = " ".join(str(concept.get("definition") or "").split())
        line = f"- 概念 {name}：{definition}" if definition else f"- 概念 {name}"
        if len(line) > 220:
            line = line[:216].rstrip() + "…"
        if used_len + len(line) + 1 > budget:
            break
        body.append(line)
        used_len += len(line) + 1

    for rel in ordered_rels:
        from_name = str(rel.get("from_name") or rel.get("from_id") or "").strip()
        to_name = str(rel.get("to_name") or rel.get("to_id") or "").strip()
        rel_type = str(rel.get("rel_type") or "").strip()
        if not from_name or not to_name or not rel_type:
            continue
        stale_note = "（来源已更新）" if rel.get("evidence_status") == "stale" else ""
        line = f"- 关系 {from_name} --[{rel_type}]--> {to_name}{stale_note}"
        if used_len + len(line) + 1 > budget:
            break
        body.append(line)
        used_len += len(line) + 1

    if not body:
        return ""
    return "\n".join([CONCEPT_MAP_CONTEXT_HEADER, *body, CONCEPT_MAP_SEED_NOTE])


def attach_concept_map_seed(prompt: str | None, block: str) -> str | None:
    """Idempotently append ``block`` to a request prompt."""
    if not block:
        return prompt
    base = str(prompt or "")
    if CONCEPT_MAP_CONTEXT_HEADER in base:
        return base
    return f"{base}\n\n{block}" if base else block
