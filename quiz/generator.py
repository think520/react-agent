import json
import logging
import re
from datetime import datetime, timezone

from rag.retriever import search_index

from .schema import Question

logger = logging.getLogger(__name__)

QUESTION_GENERATION_PROMPT = """你是一个题目生成器。根据以下课程材料，生成 {count} 道练习题。

要求：
1. 题型包括：single_choice（单选）、true_false（判断）、short_answer（简答）
2. 单选题：提供 4 个选项 A/B/C/D，答案是正确选项的字母
3. 判断题：答案是 "true" 或 "false"
4. 简答题：答案是简短的事实性短语
5. 题目应该考察理解能力，而不是死记硬背
6. 每道题标注相关概念名称
7. 分配难度：easy、medium、hard
8. 每道题提供 source_ids，只能选择课程材料中实际出现的来源编号
9. 所有内容用中文

课程材料：
{material}

严格按以下 JSON 数组格式输出，不要添加 markdown 代码块或其他文字：
[
  {{
    "type": "single_choice",
    "question": "Dijkstra 算法采用什么策略？",
    "options": ["A. 分治法", "B. 贪心策略", "C. 动态规划", "D. 回溯法"],
    "answer": "B",
    "explanation": "Dijkstra 算法每次选择距离最小的未访问顶点，属于贪心策略。",
    "concepts": ["Dijkstra 算法", "贪心算法"],
    "difficulty": "easy",
    "source_ids": ["S1"]
  }}
]"""


def _parse_json_from_llm(text: str) -> list[dict]:
    """Extract and parse JSON array from LLM response, handling common formatting issues."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()

    # Try direct parse first (ideal case: clean JSON array)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Find the first [ and matching ] using bracket depth tracking
    start = text.find("[")
    if start == -1:
        logger.warning("No JSON array found in LLM response: %.200s", text)
        return []

    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        logger.warning("Unmatched [ in LLM response: %.200s", text[start:])
        return []

    json_str = text[start : end + 1]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse JSON from LLM response: %s | raw: %.300s", e, json_str)
        # Try to fix trailing commas
        try:
            fixed = re.sub(r",\s*([}\]])", r"\1", json_str)
            data = json.loads(fixed)
        except json.JSONDecodeError:
            return []

    if not isinstance(data, list):
        logger.warning("LLM response is not a JSON array: %s", type(data).__name__)
        return []

    return data


def _validate_question(item: dict) -> bool:
    """Check that a parsed dict has the minimum required fields."""
    required = {"type", "question", "answer"}
    if not required.issubset(item.keys()):
        return False
    if item["type"] not in ("single_choice", "true_false", "short_answer"):
        return False
    if not item["question"] or not item["answer"]:
        return False
    return True


class QuestionGenerator:
    def __init__(self, workspace: str, llm_provider):
        self.workspace = workspace
        self.llm = llm_provider

    def generate_from_chunks(
        self, chunks: list[dict], count: int = 5
    ) -> list[Question]:
        """Generate questions from RAG search results."""
        if not chunks:
            return []

        # Build material text from chunks
        material_parts = []
        source_refs: dict[str, dict] = {}
        for i, chunk in enumerate(chunks[:10], 1):
            source_id = f"S{i}"
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "")
            metadata = chunk.get("metadata") or {}
            source_refs[source_id] = {
                "source_type": "local",
                "source_id": str(chunk.get("chunk_id") or source_id),
                "title": str(chunk.get("title") or metadata.get("title") or source),
                "document_id": chunk.get("document_id"),
                "chunk_id": chunk.get("chunk_id"),
                "heading": metadata.get("heading_text") or chunk.get("heading_text"),
                "page": metadata.get("page_start") or chunk.get("page_start"),
                "slide": metadata.get("slide_start") or chunk.get("slide_start"),
            }
            material_parts.append(f"[来源 {source_id}: {source}]\n{text}")
        material = "\n\n".join(material_parts)

        prompt = QUESTION_GENERATION_PROMPT.format(count=count, material=material)

        try:
            response = self.llm.complete([{"role": "user", "content": prompt}])
            raw_text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error("LLM call failed during question generation: %s", e)
            return []

        parsed = _parse_json_from_llm(raw_text)
        questions = []
        for item in parsed:
            if not _validate_question(item):
                logger.warning("Skipping invalid question item: %s", item.get("question", "?"))
                continue
            selected_sources = [
                source_refs[source_id]
                for source_id in item.get("source_ids", [])
                if source_id in source_refs
            ]
            if not selected_sources:
                selected_sources = list(source_refs.values())[:3]

            questions.append(Question(
                type=item["type"],
                question=item["question"],
                options=item.get("options", []),
                answer=item["answer"],
                explanation=item.get("explanation", ""),
                concepts=item.get("concepts", []),
                difficulty=item.get("difficulty", "medium"),
                source=selected_sources[0]["title"] if selected_sources else "",
                attribution_kind="local_extension" if selected_sources else "unverified",
                sources=selected_sources,
                created_at=datetime.now(timezone.utc).isoformat(),
            ))

        return questions[:count]

    def generate_from_query(
        self,
        query: str,
        course: str | None = None,
        count: int = 5,
        document_ids: list[str] | None = None,
    ) -> list[Question]:
        """Search RAG for relevant chunks, then generate questions."""
        try:
            if document_ids:
                from service.kb_service import KBService
                result = KBService(self.workspace).search(
                    query=query,
                    course=course,
                    top_k=8,
                    document_ids=document_ids,
                )
                chunks = result.get("results", []) if result.get("ok") else []
            else:
                chunks = search_index(self.workspace, query, course=course, top_k=8)
        except Exception as e:
            logger.error("RAG search failed: %s", e)
            return []

        if not chunks:
            logger.warning("No relevant chunks found for query: %s", query)
            return []

        return self.generate_from_chunks(chunks, count=count)
