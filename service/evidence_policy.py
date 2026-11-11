from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceDecision:
    allow: bool
    correction_prompt: str = ""
    fallback_content: str = ""


class LocalEvidencePolicy:
    """Require local evidence or an explicit no-hit disclosure."""

    max_retries = 1
    no_hit_disclosure = "资料库中未找到直接依据"

    @staticmethod
    def is_satisfied(tool_history: list[dict[str, Any]]) -> bool:
        return any(
            record.get("name") == "rag_search"
            and record.get("ok")
            and (
                record.get("data", {}).get("evidence_status") == "found"
                or bool(record.get("data", {}).get("results"))
            )
            for record in tool_history
        )

    @staticmethod
    def _has_no_hit(tool_history: list[dict[str, Any]]) -> bool:
        return any(
            record.get("name") == "rag_search"
            and record.get("ok")
            and (
                record.get("data", {}).get("evidence_status") == "no_hit"
                or record.get("data", {}).get("hit_count") == 0
            )
            for record in tool_history
        )

    def validate(
        self,
        tool_history: list[dict[str, Any]],
        response_text: str,
        retry_count: int,
    ) -> EvidenceDecision:
        if self.is_satisfied(tool_history):
            return EvidenceDecision(allow=True)
        if self._has_no_hit(tool_history) and self.no_hit_disclosure in response_text:
            return EvidenceDecision(allow=True)
        if retry_count < self.max_retries:
            if self._has_no_hit(tool_history):
                return EvidenceDecision(
                    allow=False,
                    correction_prompt=(
                        "The local library search returned no direct evidence. Begin the answer with "
                        "'资料库中未找到直接依据，以下为通用知识。' and clearly separate general "
                        "knowledge from local-source claims."
                    ),
                )
            return EvidenceDecision(
                allow=False,
                correction_prompt=(
                    "This answer must be grounded in the user's local materials, but no successful "
                    "rag_search has been completed in this turn. Call rag_search before answering. "
                    "Concept-map relationships and personal knowledge do not replace original source evidence."
                ),
            )
        if self._has_no_hit(tool_history):
            return EvidenceDecision(
                allow=False,
                fallback_content="资料库中未找到直接依据，因此当前回答不能表述为基于你的资料。",
            )
        return EvidenceDecision(
            allow=False,
            fallback_content=(
                "我还没有成功检索到本地资料，因此不能把当前回答表述为基于你的资料。"
                "请稍后重试，或明确要求使用通用知识回答。"
            ),
        )


class ConceptMapPolicy:
    """Require the graph operation implied by an explicit concept-map question."""

    max_retries = 1

    def __init__(self, required_operation: str) -> None:
        self.required_operation = required_operation

    def _is_satisfied(self, tool_history: list[dict[str, Any]]) -> bool:
        allowed_operations = {
            "query": {"search", "neighbors", "path"},
            "neighbors": {"neighbors", "path"},
            "path": {"path"},
        }[self.required_operation]
        return any(
            record.get("name") == "concept_map_query"
            and record.get("ok")
            and record.get("data", {}).get("operation") in allowed_operations
            for record in tool_history
        )

    def validate(
        self,
        tool_history: list[dict[str, Any]],
        response_text: str,
        retry_count: int,
    ) -> EvidenceDecision:
        del response_text
        if self._is_satisfied(tool_history):
            return EvidenceDecision(allow=True)
        if retry_count < self.max_retries:
            operation = "path" if self.required_operation == "path" else "neighbors" if self.required_operation == "neighbors" else "search"
            return EvidenceDecision(
                allow=False,
                correction_prompt=(
                    "The user explicitly asked about the reviewed concept map. "
                    f"Before answering, call concept_map_query with operation='{operation}'. "
                    "A search operation alone does not satisfy a relationship or path question. "
                    "If the reviewed map has no matching relationship, say so honestly."
                ),
            )
        return EvidenceDecision(
            allow=False,
            fallback_content="我还没有完成所需的知识地图查询，因此不能可靠回答这次图谱问题。请稍后重试。",
        )


class InlineQuestionPolicy:
    """E13 defense 2: practice must arrive as the server-bound card.

    A model that does not call question_generate may try to end the turn with
    "A./B./C." options in plain chat. Those options are not bound to a persisted
    question set or its sources, so the turn is redirected back to the tool path
    instead of showing unbound questions.
    """

    max_retries = 1

    _OPTION_LINE = re.compile(r"(?m)^\s*(?:[-*]\s*)?([A-Da-dＡ-Ｄａ-ｄ])[.、,，)）:：]\s*\S")
    _QUESTION_HINT = re.compile(
        r"下列|以下|以下哪|哪一?个|哪个|哪项|选择|选出|正确|错误|属于|不属于|"
        r"which|choose|select|following|correct|incorrect",
        re.IGNORECASE,
    )

    def __init__(self, *, strict: bool = False) -> None:
        """W1 E13：«strict» 决定判定灵敏度。

        无条件挂载时用严格判定 —— 它只认「成组的**短**选项出现在**结尾**，且上下文在提问」，
        不会误伤讲解里并列的「A. 从能量角度……」；用户明确要题时用宽松判定（≥2 个字母选项即算）。
        """
        self._strict = strict

    @classmethod
    def looks_like_inline_question(cls, response_text: str, *, strict: bool = False) -> bool:
        """True when the text presents at least two lettered options.

        «strict=True» adds the structural requirements described in «__init__».
        """
        labels = {match.group(1) for match in cls._OPTION_LINE.finditer(response_text)}
        if len(labels) < 2:
            return False
        if not strict:
            return True

        lines = [line for line in response_text.strip().splitlines() if line.strip()]
        if len(lines) < 3:
            # 只有选项、没有题干 —— 不像一道题。
            return False
        tail = lines[-6:]
        option_lines = [line for line in tail if cls._OPTION_LINE.match(line)]
        if len(option_lines) < 2:
            return False
        if any(len(line.strip()) > 48 for line in option_lines):
            # 真正的选项是短的；长句是解释里的并列说法。
            return False
        head = "\n".join(lines[: -len(option_lines)] or lines)
        return bool(cls._QUESTION_HINT.search(head)) or "？" in head or "?" in head

    def validate(
        self,
        tool_history: list[dict[str, Any]],
        response_text: str,
        retry_count: int,
    ) -> EvidenceDecision:
        if not self.looks_like_inline_question(response_text, strict=self._strict):
            return EvidenceDecision(allow=True)
        if any(
            record.get("name") == "question_generate" and record.get("ok")
            for record in tool_history
        ):
            return EvidenceDecision(allow=True)
        if retry_count < self.max_retries:
            return EvidenceDecision(
                allow=False,
                correction_prompt=(
                    "Do not deliver practice questions as plain text options in chat. "
                    "Call question_generate so Bobodan builds the practice-ready card; "
                    "the questions, their sources and the session are bound server-side."
                ),
            )
        return EvidenceDecision(
            allow=False,
            fallback_content=(
                "这次没能生成可用的练习卡，所以我没有把题目直接发出来。"
                "请再说明一次要练习的主题，我会重新准备。"
            ),
        )


class CitationPolicy:
    """W2-EVID-01：回答里的每个引用标签都必须来自本轮真实拿到的证据。

    允许集合 = 进入本轮前注入的证据（预检索块、用户选定的网页快照，按文本里出现的标签收集）
    ∪ 本轮 ``rag_search`` 命中 ∪ 本轮 ``web_research`` 快照。标签由 source_id 确定性
    算出（``rag.citations.cite_label``），所以不依赖模型复述编号。

    只核对「引用是不是真的」，不核对「引用是否支持结论」—— 后者是风险信号，不在这里冒充保证。
    重试用尽时不丢弃整段回答：去掉无法对应的标签并如实说明，避免把编造的出处展示给用户。
    """

    max_retries = 1
    removed_notice = "（已移除 {count} 处无法对应本轮资料的引用标记；相关表述没有可核对的出处。）"

    def __init__(self, preset_text: str = "") -> None:
        from rag.citations import cited_labels

        self._preset = set(cited_labels(preset_text))

    @staticmethod
    def _labels_from_history(tool_history: list[dict[str, Any]]) -> set[str]:
        from rag.citations import cite_label, hit_source_id

        labels: set[str] = set()
        for record in tool_history:
            if not record.get("ok"):
                continue
            data = record.get("data") or {}
            if record.get("name") == "rag_search":
                for hit in data.get("results") or []:
                    if isinstance(hit, dict) and hit_source_id(hit):
                        labels.add(cite_label(hit_source_id(hit)))
            elif record.get("name") == "web_research":
                for source in data.get("sources") or []:
                    if isinstance(source, dict) and source.get("source_id"):
                        labels.add(cite_label(str(source["source_id"])))
        return labels

    def unknown_labels(self, tool_history: list[dict[str, Any]], response_text: str) -> list[str]:
        from rag.citations import cited_labels

        allowed = self._preset | self._labels_from_history(tool_history)
        return [label for label in cited_labels(response_text) if label not in allowed]

    def validate(
        self,
        tool_history: list[dict[str, Any]],
        response_text: str,
        retry_count: int,
    ) -> EvidenceDecision:
        unknown = self.unknown_labels(tool_history, response_text)
        if not unknown:
            return EvidenceDecision(allow=True)
        listed = "、".join(f"[{label}]" for label in unknown)
        if retry_count < self.max_retries:
            return EvidenceDecision(
                allow=False,
                correction_prompt=(
                    f"回答里的引用标签 {listed} 不对应本轮检索到的任何资料。"
                    "重写回答：只使用本轮资料开头给出的标签；找不到依据的内容不要加标签，"
                    "并说明它不是来自用户的资料。"
                ),
            )
        from rag.citations import CITATION_MARKER

        cleaned = CITATION_MARKER.sub(
            lambda match: "" if match.group(1) in unknown else match.group(0),
            response_text,
        ).rstrip()
        notice = self.removed_notice.format(count=len(unknown))
        return EvidenceDecision(allow=False, fallback_content=f"{cleaned}\n\n{notice}" if cleaned else notice)


class CombinedResponsePolicy:
    """Apply multiple deterministic response requirements without merging their logic."""

    def __init__(self, *policies: Any) -> None:
        self.policies = [policy for policy in policies if policy is not None]
        self.max_retries = sum(int(getattr(policy, "max_retries", 1)) for policy in self.policies)

    def validate(
        self,
        tool_history: list[dict[str, Any]],
        response_text: str,
        retry_count: int,
    ) -> EvidenceDecision:
        for policy in self.policies:
            decision = policy.validate(tool_history, response_text, 0)
            if decision.allow:
                continue
            if retry_count < self.max_retries and decision.correction_prompt:
                return decision
            return policy.validate(
                tool_history,
                response_text,
                int(getattr(policy, "max_retries", 1)),
            )
        return EvidenceDecision(allow=True)
