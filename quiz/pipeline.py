"""出题三阶段管线：Explore → Plan → 逐题生成（W1 E5）。

设计来自参考项目 DeepTutor `deeptutor/agents/question/pipeline.py`（见
docs/Bobodan参考项目调研报告.md 的 D8/D9）：

- **Explore**：先确认资料里确实有可出题的内容。拿不到证据就**明确失败**，
  而不是安静地出 0 道题（用户会以为"生成成功但没题"）。
- **Plan**：一次 LLM 调用给出逐题模板（主题/题型/难度）。模型不可用或输出不可解析时
  用**确定性兜底**，来源如实标注为 `fallback`。
- **Quiz**：逐题生成，**每生成一道就落库并回调一次** —— 这是"每题就绪即渲染"的数据前提；
  某一道失败只跳过它，不影响后面的题。

本模块只管管线与事件；SSE 传输与界面是下一步。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

PLAN_PROMPT_MARKER = "你是出题计划器"

PLAN_PROMPT = PLAN_PROMPT_MARKER + """。根据下面的主题与要求，给出逐题模板。

主题：{topic}
题量：{count}
{extra}
只输出严格 JSON 数组，每项形如：
{{"topic": "这道题考的具体点", "question_type": "single_choice|true_false|short_answer", "difficulty": "easy|medium|hard"}}
不要输出 Markdown 代码块，不要输出解释文字。"""

_TYPES = ("single_choice", "true_false", "short_answer")


@dataclass(frozen=True)
class PlanItem:
    topic: str
    question_type: str = "single_choice"
    difficulty: str = "medium"


def default_plan(topic: str, count: int) -> list[PlanItem]:
    """确定性兜底计划：题量与题型分布固定，便于测试与离线可用。"""
    total = max(1, int(count))
    base = (topic or "").strip() or "本节内容"
    return [
        PlanItem(
            topic=base,
            question_type=_TYPES[index % len(_TYPES)],
            difficulty="easy" if index == 0 else "medium",
        )
        for index in range(total)
    ]


def _plan_from_payload(payload: Any, *, topic: str, count: int) -> list[PlanItem] | None:
    if not isinstance(payload, list):
        return None
    items: list[PlanItem] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("topic") or topic or "").strip()
        if not name:
            continue
        question_type = str(entry.get("question_type") or "single_choice").strip()
        difficulty = str(entry.get("difficulty") or "medium").strip()
        items.append(PlanItem(
            topic=name,
            question_type=question_type if question_type in _TYPES else "single_choice",
            difficulty=difficulty if difficulty in {"easy", "medium", "hard"} else "medium",
        ))
    return items[: max(1, int(count))] if items else None


def build_plan(
    topic: str,
    count: int,
    *,
    llm: Any = None,
    weak_concepts: Iterable[str] | None = None,
) -> tuple[list[PlanItem], str]:
    """Phase 2：返回 (计划, 来源)。来源是 `llm` 或 `fallback`，不猜。"""
    if llm is None:
        return default_plan(topic, count), "fallback"

    weak = [name for name in (weak_concepts or []) if str(name).strip()]
    extra = f"优先覆盖这些薄弱点：{'、'.join(weak)}\n" if weak else ""
    prompt = PLAN_PROMPT.format(topic=topic, count=count, extra=extra)
    try:
        response = llm.complete([{"role": "user", "content": prompt}])
        raw = response.content if hasattr(response, "content") else str(response)
        # 计划是 JSON **数组** —— 用能解析数组的那个入口（parse_llm_object 只认对象）。
        from core.llm_json import parse_llm_array

        parsed = parse_llm_array(raw)
    except Exception as exc:
        logger.warning("Question plan LLM call failed: %s", exc)
        parsed = None
    items = _plan_from_payload(parsed, topic=topic, count=count) if parsed is not None else None
    if items is None:
        return default_plan(topic, count), "fallback"
    return items, "llm"


def _explore(
    *,
    workspace: str,
    topic: str,
    document_ids: list[str] | None,
    course: str | None = None,
    top_k: int = 8,
) -> list[dict]:
    """Phase 1：确认有可出题的资料。检索异常按「没有证据」处理（由调用方如实报错）。

    W1 E5 修正：以前这里直接调 «search_index»，于是**完全忽略 document_ids 与 course** ——
    用户在界面上选的资料范围对逐题管线无效（可能拿到范围外的证据）。现在走
    «KBService.search»：它按 document_ids 过滤、按 course 限定，并保住可见性规则。
    """
    try:
        from service.kb_service import KBService

        result = KBService(workspace).search(
            topic,
            course=course,
            top_k=top_k,
            document_ids=list(document_ids) if document_ids else None,
        )
        if not result.get("ok"):
            return []
        return list(result.get("results") or [])
    except Exception as exc:
        logger.warning("Explore retrieval failed: %s", exc)
        return []


def run_question_pipeline(
    *,
    workspace: str,
    topic: str,
    count: int = 5,
    llm: Any = None,
    config: dict | None = None,
    document_ids: list[str] | None = None,
    course: str | None = None,
    on_event: Callable[[dict], None] | None = None,
    cancel_token: Any = None,
) -> dict[str, Any]:
    """跑完三阶段；每题就绪即落库并回调。"""
    emit = on_event or (lambda event: None)
    emit({"event": "pipeline_started", "topic": topic, "count": int(count)})

    chunks = _explore(
        workspace=workspace, topic=topic, document_ids=document_ids, course=course,
    )
    if not chunks:
        emit({"event": "pipeline_failed", "code": "no_evidence"})
        return {
            "ok": False,
            "code": "no_evidence",
            "error": "没有找到可用于出题的资料。先放进材料，或换一个更贴近资料的主题。",
            "question_ids": [],
        }
    emit({"event": "explore_done", "chunks": len(chunks)})

    plan, source = build_plan(topic, count, llm=llm)
    emit({
        "event": "quiz_plan",
        "source": source,
        "plan": [
            {"topic": item.topic, "question_type": item.question_type, "difficulty": item.difficulty}
            for item in plan
        ],
    })

    from quiz.generator import QuestionGenerator
    from quiz.store import QuizStore

    store = QuizStore(workspace)
    question_ids: list[int] = []
    total = len(plan)
    for index, item in enumerate(plan):
        if cancel_token is not None and cancel_token.is_cancelled():
            emit({"event": "pipeline_cancelled", "emitted": len(question_ids), "total": total})
            return {
                "ok": True,
                "cancelled": True,
                "question_ids": question_ids,
                "plan_source": source,
            }
        try:
            generator = QuestionGenerator(workspace, llm) if llm is not None else None
            if generator is None:
                generated: list[Any] = []
            else:
                generated = generator.generate_from_query(
                    item.topic, count=1, document_ids=document_ids,
                )
        except Exception as exc:
            logger.warning("Question %d failed: %s", index, exc)
            generated = []
        if not generated:
            emit({"event": "quiz_question_failed", "index": index, "total": total, "topic": item.topic})
            continue
        question = generated[0]
        question.id = store.add_question(question)
        question_ids.append(question.id)
        # 先落库再发事件：事件到达时题库里已经有这道题（"每题就绪即渲染"）。
        emit({
            "event": "quiz_question_emitted",
            "index": index,
            "total": total,
            "question_id": question.id,
            "topic": item.topic,
            "question": {
                "id": question.id,
                "type": question.type,
                "question": question.question,
                "options": list(question.options or []),
            },
        })

    emit({"event": "pipeline_done", "question_ids": question_ids, "total": total})
    return {
        "ok": True,
        "cancelled": False,
        "question_ids": question_ids,
        "plan_source": source,
        "failed": total - len(question_ids),
    }
