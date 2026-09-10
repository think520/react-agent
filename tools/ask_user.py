"""Agent tool: ask the user a structured question and pause the turn (E4).

The question is registered in the interaction store, so its lifecycle
(registered -> awaiting_input -> answered -> graded) survives a reload or a
restart. The card shown to the user never carries a correct option.
"""

import uuid

from tools.base import ToolResult, register_tool


def _get_workspace(session=None) -> str:
    return getattr(session, "workspace_root", None) or "."


def _normalize_questions(raw) -> list[dict]:
    normalized: list[dict] = []
    for index, item in enumerate(raw or [], 1):
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or item.get("question") or "").strip()
        if not prompt:
            continue
        options = [
            str(option).strip()
            for option in (item.get("options") or [])
            if str(option).strip()
        ]
        entry = {
            "id": str(item.get("id") or f"q{index}"),
            "prompt": prompt[:400],
            "options": options[:8],
            "multi_select": bool(item.get("multi_select")),
        }
        expected = str(item.get("answer") or "").strip()
        if expected:
            # Kept only for deterministic grading; never sent to the client.
            entry["answer"] = expected
        normalized.append(entry)
    return normalized[:5]


def ask_user(questions: list[dict], session=None) -> ToolResult:
    """Ask the user structured questions; the answer arrives in a later turn."""
    from service.interaction_service import InteractionService

    normalized = _normalize_questions(questions)
    if not normalized:
        return ToolResult(ok=False, content="ask_user needs at least one question with a prompt.")

    service = InteractionService(_get_workspace(session))
    interaction_id = uuid.uuid4().hex
    service.register(
        interaction_id,
        chat_session_id=getattr(session, "session_id", "") or "",
        questions=normalized,
    )
    service.mark_awaiting(interaction_id)

    # E13 defense 3: the card is rebuilt from the persisted record and the
    # correct option is stripped, so the model cannot leak the answer.
    public_questions = [
        {key: value for key, value in question.items() if key != "answer"}
        for question in normalized
    ]
    artifact = {
        "type": "ask_user",
        "artifact_id": interaction_id,
        "status": "awaiting_input",
        "questions": public_questions,
    }
    return ToolResult(
        ok=True,
        content=(
            "已向用户展示问题卡，本轮到此暂停。等用户在卡片里作答后再继续；"
            "不要替用户选择，也不要在本轮继续推进。"
        ),
        artifacts=[artifact],
    )


register_tool(
    name="ask_user",
    description=(
        "需要用户先做明确选择才能继续时，展示问题卡并暂停本轮。"
        "适合让学习者选择学习方向、难度或下一步；可以自行判断的普通提问不要用。"
    ),
    params_schema={
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "1-5 个问题，每题含 prompt，可选 options 与 multi_select。",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "prompt": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "multi_select": {"type": "boolean"},
                        "answer": {"type": "string", "description": "可选：正确选项，仅用于确定性判分，不会展示给用户"},
                    },
                    "required": ["prompt"],
                },
            }
        },
        "required": ["questions"],
    },
    func=ask_user,
)
