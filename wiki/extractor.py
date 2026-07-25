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
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Prompt
# ------------------------------------------------------------------

_CONCEPT_PROMPT = """\
你是一位知识图谱编辑。只扫描当前章节中明确出现、值得学习的概念，不分析概念关系。

资料标题：{title}
章节：{section_title}

章节原文：
{content}

规则：
1. 核心概念必须是本章的主要学习对象；细分概念是其组成、方法或具体术语。
2. 每个概念必须给出能在章节原文中逐字找到的 excerpt；没有原文证据就不要提交。
3. 不要为了凑数量引入常识性概念或原文未提及的概念。

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
  "tags": ["术语1", "术语2"]
}}
"""

_RELATION_PROMPT = """\
你是一位知识图谱关系编辑。只判断下面这些已识别概念之间，在给定原文中是否存在明确语义关系。

资料标题：{title}
范围：{section_title}
候选概念：{concepts}

证据原文：
{content}

规则：
1. 只输出有原文 excerpt 直接支撑的关系。
2. rel_type 只能是：属于 | 前置知识 | 组成部分 | 对比 | 应用于 | 来源于 | 影响 | 优化 | 示例。
3. from/to 必须来自候选概念，不要新增概念。

返回 JSON：
{{"relationships":[{{"from":"概念A","to":"概念B","rel_type":"组成部分","excerpt":"原文证据"}}]}}
"""

_SUPPLEMENT_CONCEPT_PROMPT = """\
第一次章节扫描得到的核心概念偏少。请只补充原文中明确出现、但被遗漏的学习概念。
已有概念：{concepts}
原文：
{content}
每个补充概念必须包含可逐字定位的 excerpt；没有遗漏就返回空数组。
返回 JSON：{{"core_concepts":[],"detail_concepts":[],"tags":[]}}
"""

_SUPPLEMENT_RELATION_PROMPT = """\
第一次关系分析得到的连接偏少。请只检查下列概念及其原文证据之间是否遗漏了关系。
概念与证据：
{content}
关系必须有 excerpt 支撑，不能仅凭常识或语义相似度推断。
rel_type 只能是：属于 | 前置知识 | 组成部分 | 对比 | 应用于 | 来源于 | 影响 | 优化 | 示例。
返回 JSON：{{"relationships":[]}}
"""

_VALID_REL_TYPES = {"属于", "前置知识", "组成部分", "对比", "应用于", "来源于", "影响", "优化", "示例"}


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
        sections: list[dict[str, Any]] | None = None,
        progress: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Run extraction and return a structured result.

        Returns
        -------
        dict with keys:
          ``core_concepts``, ``detail_concepts``, ``relationships``, ``tags``,
          ``document_id``, ``document_title``, ``error`` (only on failure)
        """
        del document_path
        section_items = _normalise_sections(sections, content, document_title)
        _notify(progress, "scanning_sections", section_count=len(section_items), completed_sections=0)
        section_results: list[dict[str, Any]] = []
        failed_sections: list[dict[str, Any]] = []
        tags: list[str] = []
        for index, section in enumerate(section_items):
            prompt = _CONCEPT_PROMPT.format(
                title=document_title,
                section_title=section["title"],
                content=section["text"],
            )
            parsed, error = self._call_json(prompt, retries=1)
            if parsed is None:
                failed_sections.append({
                    "index": index,
                    "title": section["title"],
                    "chunk_id": section.get("chunk_id"),
                    "error": error or "JSON parse failed",
                })
            else:
                validated = _validate_and_clip(parsed, document_id, document_title)
                section_results.append({"section": section, **validated})
                tags.extend(validated["tags"])
            _notify(
                progress,
                "scanning_sections",
                section_count=len(section_items),
                completed_sections=index + 1,
                failed_sections=len(failed_sections),
            )

        if not section_results:
            error = failed_sections[0]["error"] if failed_sections else "没有识别到可用章节"
            return _error_result(document_id, document_title, error)

        _notify(progress, "merging_concepts", section_count=len(section_items))
        core = _dedupe_concepts([item for result in section_results for item in result["core_concepts"]])
        detail = _dedupe_concepts([item for result in section_results for item in result["detail_concepts"]], excluded={item["name"].casefold() for item in core})

        _notify(progress, "analyzing_local_relationships", section_count=len(section_items))
        relationships: list[dict[str, Any]] = []
        for result in section_results:
            local_concepts = [*result["core_concepts"], *result["detail_concepts"]]
            if len(local_concepts) < 2:
                continue
            parsed, _ = self._call_json(_RELATION_PROMPT.format(
                title=document_title,
                section_title=result["section"]["title"],
                concepts="、".join(item["name"] for item in local_concepts),
                content=result["section"]["text"],
            ))
            if parsed:
                relationships.extend(_filter_rels(parsed.get("relationships", [])))

        _notify(progress, "analyzing_cross_section_relationships", section_count=len(section_items))
        if len(section_results) > 1 and len(core) >= 2:
            evidence_text = "\n".join(f"- {item['name']}：{item['excerpt']}" for item in core)
            parsed, _ = self._call_json(_RELATION_PROMPT.format(
                title=document_title,
                section_title="跨章节核心概念",
                concepts="、".join(item["name"] for item in core),
                content=evidence_text,
            ))
            if parsed:
                relationships.extend(_filter_rels(parsed.get("relationships", [])))

        all_names = {item["name"] for item in [*core, *detail]}
        relationships = _dedupe_relationships([
            item for item in relationships
            if item["from"] in all_names and item["to"] in all_names and item.get("excerpt")
        ])

        _notify(progress, "quality_check", section_count=len(section_items))
        quality = _quality_report(core, relationships, len(section_items))
        supplemented = False
        if quality["failure_type"]:
            supplemented = True
            _notify(progress, "supplementing", failure_type=quality["failure_type"])
            if quality["failure_type"] == "concepts":
                weakest = sorted(section_results, key=lambda item: len(item["core_concepts"]))[:3]
                supplement_content = "\n\n".join(
                    f"## {item['section']['title']}\n{item['section']['text']}" for item in weakest
                )
                parsed, _ = self._call_json(_SUPPLEMENT_CONCEPT_PROMPT.format(
                    concepts="、".join(item["name"] for item in [*core, *detail]),
                    content=supplement_content,
                ))
                if parsed:
                    extra = _validate_and_clip(parsed, document_id, document_title)
                    core = _dedupe_concepts([*core, *extra["core_concepts"]])
                    detail = _dedupe_concepts([*detail, *extra["detail_concepts"]], excluded={item["name"].casefold() for item in core})
                    tags.extend(extra["tags"])
            else:
                evidence_text = "\n".join(
                    f"- {item['name']}：{item['excerpt']}" for item in [*core, *detail] if item.get("excerpt")
                )
                parsed, _ = self._call_json(_SUPPLEMENT_RELATION_PROMPT.format(content=evidence_text))
                if parsed:
                    all_names = {item["name"] for item in [*core, *detail]}
                    relationships = _dedupe_relationships([
                        *relationships,
                        *[
                            item for item in _filter_rels(parsed.get("relationships", []))
                            if item["from"] in all_names and item["to"] in all_names and item.get("excerpt")
                        ],
                    ])
            quality = _quality_report(core, relationships, len(section_items))

        _notify(progress, "ready_for_review", section_count=len(section_items))
        warnings = []
        if failed_sections:
            warnings.append(f"{len(failed_sections)} 个章节提取失败，可稍后单独重试")
        if quality["failure_type"]:
            warnings.append("系统已定向补提一次，候选概念或关系仍可能偏少")
        return {
            "document_id": document_id,
            "document_title": document_title,
            "core_concepts": core,
            "detail_concepts": detail,
            "relationships": relationships,
            "tags": list(dict.fromkeys(tags))[:40],
            "error": None,
            "section_count": len(section_items),
            "failed_sections": failed_sections,
            "warnings": warnings,
            "quality": quality,
            "supplemented": supplemented,
        }

    def _call_json(self, prompt: str, *, retries: int = 0) -> tuple[dict[str, Any] | None, str]:
        error = ""
        for _ in range(retries + 1):
            try:
                response = self._llm.complete([{"role": "user", "content": prompt}])
                parsed = _parse_response(response.content or "")
                if parsed is not None:
                    return parsed, ""
                error = "JSON parse failed"
            except Exception as exc:
                error = str(exc)
                logger.warning("ConceptExtractor LLM call failed: %s", exc)
        return None, error


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


def _notify(progress: Callable[[str, dict[str, Any]], None] | None, stage: str, **payload: Any) -> None:
    if progress is not None:
        progress(stage, payload)


def _normalise_sections(
    sections: list[dict[str, Any]] | None,
    content: str,
    document_title: str,
) -> list[dict[str, Any]]:
    if sections:
        result = []
        for index, section in enumerate(sections):
            text = str(section.get("text") or "").strip()
            if not text:
                continue
            result.append({
                "chunk_id": section.get("chunk_id") or section.get("id") or f"section-{index + 1}",
                "title": str(section.get("heading") or section.get("title") or f"第 {index + 1} 节"),
                "text": text,
            })
        if result:
            return result
    chunks = []
    parts = [part.strip() for part in re.split(r"\n{2,}(?=#|第.+节|[一二三四五六七八九十]+、)", content) if part.strip()]
    if not parts:
        parts = [content.strip()]
    for index, part in enumerate(parts):
        heading = part.splitlines()[0].strip("# ")[:80] if part.splitlines() else document_title
        chunks.append({"chunk_id": f"section-{index + 1}", "title": heading or document_title, "text": part})
    return chunks


def _dedupe_concepts(items: list[dict[str, Any]], *, excluded: set[str] | None = None) -> list[dict[str, Any]]:
    seen = set(excluded or set())
    result = []
    for item in items:
        key = item["name"].casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result[:12]


def _dedupe_relationships(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = (item["from"].casefold(), item["to"].casefold(), item["rel_type"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result[:40]


def _minimum_core_count(section_count: int) -> int:
    if section_count <= 2:
        return 2
    if section_count <= 5:
        return 3
    return 4


def _quality_report(
    core: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    section_count: int,
) -> dict[str, Any]:
    min_core = _minimum_core_count(section_count)
    core_names = {item["name"] for item in core}
    connected = {
        endpoint
        for rel in relationships
        for endpoint in (rel["from"], rel["to"])
        if endpoint in core_names
    }
    isolated_count = max(0, len(core_names - connected))
    isolated_ratio = isolated_count / len(core_names) if core_names else 1.0
    failure_type = None
    if len(core) < min_core:
        failure_type = "concepts"
    elif len(relationships) < len(core) * 0.5:
        failure_type = "relationships"
    elif isolated_ratio > 0.4:
        failure_type = "isolated"
    return {
        "minimum_core_concepts": min_core,
        "core_count": len(core),
        "relationship_count": len(relationships),
        "isolated_core_count": isolated_count,
        "isolated_core_ratio": round(isolated_ratio, 3),
        "failure_type": failure_type,
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
