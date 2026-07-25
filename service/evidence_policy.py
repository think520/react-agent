from __future__ import annotations

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
