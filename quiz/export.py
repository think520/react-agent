"""E18 / D7: back the bank up, and write it out as Markdown.

Two different jobs share this module:

* bank_backup / restore_bank copy the bank rows, so bookmarks and named sets --
  which exist nowhere else in the product -- cannot be lost.
* bank_to_markdown renders the bank for a human, and is the one place that
  honours the D9 third-party rule: a question whose source is marked
  third_party is excluded unless the caller asks for it, and is labelled when
  it is included, because re-distributing it would not be ours to do.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from quiz.store import QuizStore

BACKUP_SCHEMA_VERSION = 1
BACKUP_KIND = "bobodan-question-bank"

_TYPE_LABELS = {"single_choice": "单选", "true_false": "判断", "short_answer": "简答"}
_STATE_LABELS = {
    "unanswered": "未作答",
    "correct": "答对",
    "partial": "基本正确",
    "incorrect": "错题",
}
_STATE_ORDER = ("incorrect", "partial", "unanswered", "correct")


def question_sources(item: dict) -> list[dict]:
    """The source refs of a bank item, wherever they were handed to us from."""
    attribution = item.get("attribution") or {}
    sources = attribution.get("sources") or item.get("sources") or []
    return [source for source in sources if isinstance(source, dict)]


def is_third_party(item: dict) -> bool:
    """D9: a question lifted off a page is third-party content."""
    return any(bool(source.get("third_party")) for source in question_sources(item))


def bank_backup(store: QuizStore) -> dict:
    return {
        "kind": BACKUP_KIND,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tables": store.dump_bank(),
    }


def restore_bank(store: QuizStore, payload: Any) -> dict:
    """Validate a backup file, then put it back.

    Raises ValueError with a sentence a user can act on, so the API never has to
    guess what was wrong with the file.
    """
    if not isinstance(payload, dict):
        raise ValueError("备份内容不是一个对象。")
    if payload.get("kind") != BACKUP_KIND:
        raise ValueError("这不是 Bobodan 题库的备份文件。")
    version = payload.get("schema_version")
    if version != BACKUP_SCHEMA_VERSION:
        raise ValueError(
            f"备份版本 {version} 与当前版本 {BACKUP_SCHEMA_VERSION} 不一致，无法恢复。"
        )
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("备份内容缺少 tables。")
    return store.restore_bank(tables)


def _source_label(item: dict) -> str:
    attribution = item.get("attribution") or {}
    kind = attribution.get("kind") or item.get("attribution_kind") or ""
    titles = [
        str(source.get("title") or source.get("url") or "")
        for source in question_sources(item)
    ]
    titles = [title for title in titles if title]
    if not titles:
        return kind or "未标注来源"
    joined = "、".join(titles[:3])
    return f"{kind} · {joined}"


def _question_block(item: dict, index: int) -> list[str]:
    type_label = _TYPE_LABELS.get(item.get("type")) or item.get("type") or "题目"
    text = item.get("question") or ""
    lines = [f"{index}. **[{type_label}] {text}**"]
    for option in item.get("options") or []:
        lines.append(f"   - {option}")
    attempt = item.get("last_attempt") or {}
    if attempt:
        given = attempt.get("user_answer") or "（空）"
        lines.append(f"   - 你的答案：{given}")
    answer = item.get("answer")
    if answer:
        lines.append(f"   - 参考答案：{answer}")
    explanation = item.get("explanation")
    if explanation:
        lines.append(f"   - 解析：{explanation}")
    concepts = item.get("concepts") or []
    if concepts:
        concept_text = "、".join(concepts)
        lines.append(f"   - 知识点：{concept_text}")
    lines.append(f"   - 来源：{_source_label(item)}")
    if is_third_party(item):
        lines.append("   - ⚠ 第三方题目（联网来源）：题面来自外部页面，请勿再分发。")
    return lines


def bank_to_markdown(
    items: list[dict],
    *,
    title: str = "题库导出",
    include_third_party: bool = False,
    excluded_third_party: int = 0,
    generated_at: str | None = None,
) -> str:
    """Render bank items as Markdown, grouped by state (D7 picks the format)."""
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    quoted_stamp = chr(34) + stamp + chr(34)
    lines = [
        "---",
        f"title: {title}",
        f"date: {quoted_stamp}",
        "type: question-bank",
        "---",
        "",
        f"# {title} — {stamp}",
        "",
    ]
    if include_third_party:
        lines.append(f"共 {len(items)} 题；其中第三方（联网来源）题目已逐条标注。")
    elif excluded_third_party:
        lines.append(
            f"共 {len(items)} 题；按要求排除了 {excluded_third_party} 道第三方（联网来源）题目。"
        )
    else:
        lines.append(f"共 {len(items)} 题。")
    lines.append("")

    grouped: dict[str, list[dict]] = {state: [] for state in _STATE_ORDER}
    for item in items:
        grouped.setdefault(item.get("state") or "correct", []).append(item)

    for state in _STATE_ORDER:
        bucket = grouped.get(state) or []
        if not bucket:
            continue
        lines.append(f"## {_STATE_LABELS.get(state, state)}（{len(bucket)}）")
        lines.append("")
        for index, item in enumerate(bucket, 1):
            lines.extend(_question_block(item, index))
        lines.append("")

    if not items:
        lines.append("没有符合条件的题目。")
        lines.append("")
    return "\n".join(lines)
