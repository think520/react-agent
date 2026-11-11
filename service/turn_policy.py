"""每一轮对话的证据策略：预检索 + 运行时响应门禁（Web 与 CLI 共用）。

以前这些函数是 ``web/backend/routers/chat.py`` 的私有函数，CLI 根本没有接：命令行对话只靠
prompt 约束，违反「evidence_policy + AgentLoop 结束前验证构成运行时证据门禁，Prompt 只是
指导」的契约（2026-11-11 审查）。现在两个入口都调 :func:`prepare_turn`。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from service.evidence_policy import (
    CitationPolicy,
    CombinedResponsePolicy,
    ConceptMapPolicy,
    InlineQuestionPolicy,
    LocalEvidencePolicy,
)
from service.kb_service import KBService

logger = logging.getLogger(__name__)


def requires_local_evidence(
    message: str,
    *,
    has_document_scope: bool,
) -> bool:
    normalized = message.lower()
    bypass_phrases = (
        "不查资料",
        "不要查资料",
        "不用资料",
        "通用知识",
        "without searching",
        "general knowledge only",
    )
    if any(phrase in normalized for phrase in bypass_phrases):
        return False
    map_only_phrases = (
        "知识地图里",
        "知识地图上",
        "图谱里",
        "图谱上",
        "concept map",
    )
    local_phrases = (
        "根据资料",
        "基于资料",
        "资料中",
        "原文",
        "这篇文档",
        "当前文档",
        "基于此文档",
        "我的资料",
        "课程资料",
        "according to the document",
        "based on the document",
        "my materials",
    )
    if any(phrase in normalized for phrase in local_phrases):
        return True
    if any(phrase in normalized for phrase in map_only_phrases):
        return False
    return has_document_scope


def requests_practice(message: str) -> bool:
    """True when the user is asking for questions/a quiz in this turn."""
    normalized = message.lower()
    practice_phrases = (
        "出题",
        "道题",
        "出几道",
        "练几道",
        "来点题",
        "来几道",
        "给点题",
        "做题",
        "刷题",
        "刷几道",
        "练习",
        "练一练",
        "练练",
        "测验",
        "小测",
        "自测",
        "考考我",
        "考我",
        "测测我",
        "测一测",
        "检验一下",
        "检查一下我",
        "quiz",
        "practice",
        "exercise",
        "drill me",
        "test me",
        "test my",
        "generate questions",
        "some questions",
    )
    return any(phrase in normalized for phrase in practice_phrases)


def wants_kb_seed(message: str, *, has_document_scope: bool) -> bool:
    """W1 E12：哪些轮次值得"进循环前先检索一次"（冷启动）。

    出题轮不塞（练习走服务端绑定的卡片）；其余"像在问知识"的轮次才预检索。
    """
    if requests_practice(message):
        return False
    if requires_local_evidence(message, has_document_scope=has_document_scope):
        return True
    text = (message or "").strip()
    if len(text) < 4:
        return False
    if "?" in text or "？" in text:
        return True
    return any(
        word in text
        for word in ("什么", "为什么", "怎么", "如何", "解释", "区别", "讲讲", "对比", "原理")
    )


def kb_seed_for(
    message: str,
    *,
    workspace: str,
    config: dict,
    has_document_scope: bool,
    document_ids: list[str] | None = None,
    preferred_document_ids: list[str] | None = None,
    top_k: int = 4,
) -> str:
    """W1 E12 / D13：进循环前的预检索。**失败就当作没有**（绝不拖垮这一轮）。

    与 ``rag_search`` 走同一条可见性路径（``KBService.search`` + ``collection="material"``
    + 本轮资料范围）：预检索块里的片段会被引用门禁当作本轮证据，范围外资料或 Wiki 页
    不能借这条路进入回答（2026-11-11 审查）。
    """
    from core.prompt_blocks import build_kb_seed_block

    if not wants_kb_seed(message, has_document_scope=has_document_scope):
        return ""
    try:
        result = KBService(workspace).search(
            query=message,
            top_k=top_k,
            document_ids=document_ids or None,
            preferred_document_ids=preferred_document_ids or None,
            collection="material",
            config=config,
        )
    except Exception as exc:  # pragma: no cover - 具体异常类型依检索实现而定
        logger.warning("KB seed retrieval failed: %s", exc)
        return ""
    if not result.get("ok"):
        return ""
    return build_kb_seed_block(result.get("results") or [])


def build_response_policies(message: str, *, has_document_scope: bool) -> list:
    """组装这一轮要挂的响应策略（W1 E13）。

    - 本地证据 / 概念地图策略仍按语义触发（它们问的是"这一轮该不该用资料或图谱"）。
    - **出题卡防绕过（防线②）无条件挂载**：它检测的是**模型输出**（纯文本 A/B/C 收尾），
      而旧实现把挂载挂在用户措辞上 —— 措辞表漏了就能绕过。现在措辞只决定**灵敏度**：
      明确要题时用宽松判定，否则用严格判定（成组短选项在结尾且上下文在提问）。
    """
    policies: list = []
    if requires_local_evidence(message, has_document_scope=has_document_scope):
        policies.append(LocalEvidencePolicy())
    policies.append(InlineQuestionPolicy(strict=not requests_practice(message)))
    operation = required_concept_map_operation(message)
    if operation:
        policies.append(ConceptMapPolicy(operation))
    return policies


def required_concept_map_operation(message: str) -> str | None:
    normalized = message.lower()
    map_phrases = (
        "知识地图",
        "知识图谱",
        "图谱里",
        "图谱上",
        "concept map",
        "knowledge graph",
    )
    if not any(phrase in normalized for phrase in map_phrases):
        return None
    path_phrases = ("路径", "怎么连接", "如何连接", "最短路", "path")
    if any(phrase in normalized for phrase in path_phrases):
        return "path"
    relationship_phrases = (
        "关系",
        "相关",
        "关联",
        "相连",
        "连接",
        "邻居",
        "周围",
        "related",
        "relationship",
        "neighbor",
    )
    if any(phrase in normalized for phrase in relationship_phrases):
        return "neighbors"
    return "query"


@dataclass(frozen=True)
class TurnPolicy:
    """一轮对话进入 AgentLoop 前要准备好的两样东西。"""

    kb_seed: str
    response_guard: CombinedResponsePolicy


def prepare_turn(
    message: str,
    *,
    workspace: str,
    config: dict,
    document_ids: list[str] | None = None,
    preferred_document_ids: list[str] | None = None,
    preset_evidence: str = "",
) -> TurnPolicy:
    """组装预检索块与响应门禁。

    ``preset_evidence`` 是进入本轮前就交给模型的其它证据文本（例如用户选定的网页快照），
    其中的引用标签与预检索块一起算作本轮允许引用的证据。
    """
    has_document_scope = bool(document_ids or preferred_document_ids)
    policies = build_response_policies(message, has_document_scope=has_document_scope)
    kb_seed = kb_seed_for(
        message,
        workspace=workspace,
        config=config,
        has_document_scope=has_document_scope,
        document_ids=document_ids,
        preferred_document_ids=preferred_document_ids,
    )
    # W2-EVID-01：引用门禁无条件挂载（它只看回答里出现的标签）。
    policies.append(CitationPolicy(preset_text="\n".join([kb_seed or "", preset_evidence or ""])))
    return TurnPolicy(kb_seed=kb_seed, response_guard=CombinedResponsePolicy(*policies))
