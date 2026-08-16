"""before_turn memory injection lifecycle (AG-3.1).

Builds a bounded personalization injection from confirmed personal knowledge
and deterministic learning state (mastery / weak points). The injection only
adjusts explanation style and never overrides source evidence — the evidence
gate is a separate checkpoint. Extraction stays deterministic (no LLM pass).

Token budget defaults to 1500 and is configurable.
"""

from __future__ import annotations

from typing import Any

DEFAULT_TOKEN_BUDGET = 1500
# Coarse CJK/latin-mixed heuristic: ~1 token per 4 characters.
CHARS_PER_TOKEN = 4

_MARKER = "<!-- bobodan:confirmed-personal-knowledge -->"
_PREFIX = (
    "The following entries are confirmed user knowledge or deterministic "
    "mastery summaries. Use them only when relevant, never override source "
    "evidence, and do not reveal internal identifiers."
)


def estimate_tokens(text: str) -> int:
    """Rough token estimate for budget checks (not a real tokenizer)."""
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


class MemoryInjector:
    """Deterministic personalization injector with a token budget."""

    def __init__(
        self,
        workspace: str,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self.workspace = workspace
        self.token_budget = max(1, token_budget)

    @property
    def _char_budget(self) -> int:
        return self.token_budget * CHARS_PER_TOKEN

    def retrieve(self, query: str) -> tuple[str, list[dict[str, Any]]]:
        """Return (content, references) within the token budget."""
        from memory.personal_store import PersonalKnowledgeStore

        store = PersonalKnowledgeStore(self.workspace)
        pinned = [
            item for item in store.list_items(scope="global", limit=100)
            if item.get("pinned")
        ][:3]
        relevant = store.list_items(query=query, limit=8)
        seen = {item["id"] for item in pinned}
        selected = pinned + [item for item in relevant if item["id"] not in seen][:5]

        lines: list[str] = []
        refs: list[dict[str, Any]] = []
        used = 0
        for item in selected:
            line = f"- [{item['scope']}/{item['kind']}] {item['title']}: {item['content']}"
            if used + len(line) > self._char_budget:
                break
            lines.append(line)
            used += len(line)
            refs.append({
                "id": item["id"], "title": item["title"], "scope": item["scope"],
                "kind": item["kind"], "content": item["content"],
                "updated_at": item["updated_at"],
            })

        # Deterministic mastery summary (weak points) — no LLM extraction.
        try:
            from learning.store import LearningStore

            mastery = LearningStore(self.workspace).list_mastery(limit=30)
            normalized_query = query.casefold()
            asks_for_status = any(
                word in normalized_query
                for word in ("复习", "练习", "薄弱", "掌握", "review", "practice")
            )
            relevant_mastery = [
                item for item in mastery
                if item.concept.casefold() in normalized_query
                or normalized_query in item.concept.casefold()
                or (asks_for_status and item.status in {"learning", "needs_review"})
            ]
            ranked = sorted(
                relevant_mastery,
                key=lambda item: (
                    0 if item.concept.casefold() in normalized_query else 1,
                    item.score,
                    item.updated_at,
                ),
            )[:5]
            if ranked:
                lines.append("掌握度摘要：")
            for item in ranked:
                line = f"- {item.concept}: {item.status}, {round(item.score * 100)}%"
                if used + len(line) > self._char_budget:
                    break
                lines.append(line)
                used += len(line)
                refs.append({
                    "id": f"mastery:{item.concept}",
                    "title": item.concept,
                    "scope": "library",
                    "kind": "mastery",
                    "content": f"{item.status}, {round(item.score * 100)}%",
                    "updated_at": item.updated_at,
                })
        except Exception:
            # Learning state is optional; a failure must not break the turn.
            pass

        return "\n".join(lines), refs

    def build_injection(self, query: str) -> str | None:
        """Build the wrapped system-prompt fragment, or None when empty."""
        content, _references = self.retrieve(query)
        if not content.strip():
            return None
        return f"{_MARKER}\n{_PREFIX}\n{content}"

    def before_turn(self, session: Any, user_input: str) -> str | None:
        """Hook-compatible entry point (called at the loop's before_turn)."""
        workspace = getattr(session, "workspace_root", None) or self.workspace
        if workspace != self.workspace:
            injector = MemoryInjector(workspace, token_budget=self.token_budget)
            return injector.build_injection(user_input)
        return self.build_injection(user_input)
