"""Concept extractor — P5E.6 knowledge map.

Calls the LLM to extract concept candidates (core + detail) and their
relationships from a single document. Results are stored as candidates
in ConceptStore for user review before entering the official graph.

Extraction constraints (from design doc §2.4):
  - core concepts:   3–8 per document
  - detail concepts: up to 12 per document
  - relationships:   only evidence-backed ones; others silently dropped
  - remaining terms: returned as ``tags`` (not stored in graph)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Prompt
# ------------------------------------------------------------------

_EXTRACT_PROMPT = """\
你是一位知识图谱编辑，任务是从一段文字中提取概念候选和它们之间的关系。

资料标题：{title}
资料路径：{path}

内容（节选）：
{content}

规则：
1. 核心概念（core）：3–8 个，必须有明确定义和原文证据。
2. 细分概念（detail）：最多 12 个，粒度更小的子概念。
3. 关系只提交有原文支撑的；没有证据的关系直接忽略。
4. 系统关系类型（rel_type 字段只能是以下之一）：
   属于 | 前置知识 | 组成部分 | 对比 | 应用于 | 来源于
5. 其余术语放到 tags 数组，不占用概念槽位。

返回 JSON（仅 JSON，不加注释或代码块）：
{{
  "core_concepts": [
    {{
      "name": "概念名",
      "definition": "一句话定义",
      "excerpt": "原文摘录（15–60 字）",
      "confidence": "high|medium|low"
    }}
  ],
  "detail_concepts": [
    {{
      "name": "细分概念名",
      "definition": "一句话定义",
      "excerpt": "原文摘录（10–40 字）",
      "confidence": "high|medium|low"
    }}
  ],
  "relationships": [
    {{
      "from": "概念名 A",
      "to": "概念名 B",
      "rel_type": "前置知识",
      "excerpt": "支撑该关系的原文摘录"
    }}
  ],
  "tags": ["术语1", "术语2"]
}}
"""

_VALID_REL_TYPES = {"属于", "前置知识", "组成部分", "对比", "应用于", "来源于"}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class ConceptExtractor:
    """Extract concept candidates from a single document via LLM."""

    def __init__(self, llm_provider: Any) -> None:
        """
        Parameters
        ----------
        llm_provider : LLMProvider
            Any provider implementing ``complete(messages) -> LLMResponse``.
        """
        self._llm = llm_provider

    def extract(
        self,
        *,
        document_id: str,
        document_title: str,
        document_path: str,
        content: str,
        max_chars: int = 6000,
    ) -> dict[str, Any]:
        """Run extraction and return a structured result.

        Returns
        -------
        dict with keys:
          ``core_concepts``, ``detail_concepts``, ``relationships``, ``tags``,
          ``document_id``, ``document_title``, ``error`` (only on failure)
        """
        snippet = content[:max_chars]
        prompt = _EXTRACT_PROMPT.format(
            title=document_title,
            path=document_path,
            content=snippet,
        )
        try:
            response = self._llm.complete(
                [{"role": "user", "content": prompt}]
            )
            raw = response.content or ""
        except Exception as exc:
            logger.warning("ConceptExtractor LLM call failed: %s", exc)
            return _error_result(document_id, document_title, str(exc))

        parsed = _parse_response(raw)
        if parsed is None:
            logger.warning(
                "ConceptExtractor: could not parse LLM output for %s",
                document_title,
            )
            return _error_result(document_id, document_title, "JSON parse failed")

        return _validate_and_clip(parsed, document_id, document_title)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _parse_response(raw: str) -> dict[str, Any] | None:
    """Extract the JSON object from the LLM reply."""
    # Strip markdown fences if present
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1).strip()
    # Find first {...}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _validate_and_clip(
    data: dict[str, Any],
    document_id: str,
    document_title: str,
) -> dict[str, Any]:
    """Enforce extraction constraints and sanitise types."""
    core = _clip_concepts(data.get("core_concepts", []), limit=8)
    detail = _clip_concepts(data.get("detail_concepts", []), limit=12)
    rels = _filter_rels(data.get("relationships", []))
    tags = [str(t) for t in data.get("tags", []) if t]

    all_names = {c["name"] for c in core} | {c["name"] for c in detail}
    # Drop rels referencing unknown names
    rels = [r for r in rels if r["from"] in all_names and r["to"] in all_names]

    return {
        "document_id": document_id,
        "document_title": document_title,
        "core_concepts": core,
        "detail_concepts": detail,
        "relationships": rels,
        "tags": tags[:40],
        "error": None,
    }


def _clip_concepts(items: list[Any], limit: int) -> list[dict[str, Any]]:
    result = []
    for item in items[:limit]:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        result.append({
            "name": str(item["name"]).strip(),
            "definition": str(item.get("definition", "")).strip(),
            "excerpt": str(item.get("excerpt", "")).strip(),
            "confidence": item.get("confidence", "medium")
            if item.get("confidence") in {"high", "medium", "low"}
            else "medium",
        })
    return result


def _filter_rels(items: list[Any]) -> list[dict[str, Any]]:
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rel_type = str(item.get("rel_type", "")).strip()
        if rel_type not in _VALID_REL_TYPES:
            continue
        if not item.get("from") or not item.get("to"):
            continue
        result.append({
            "from": str(item["from"]).strip(),
            "to": str(item["to"]).strip(),
            "rel_type": rel_type,
            "excerpt": str(item.get("excerpt", "")).strip(),
        })
    return result


def _error_result(document_id: str, document_title: str, msg: str) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "document_title": document_title,
        "core_concepts": [],
        "detail_concepts": [],
        "relationships": [],
        "tags": [],
        "error": msg,
    }
