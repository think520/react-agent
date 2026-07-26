"""Agent tool for user-confirmed personal-knowledge proposals."""

import uuid

from tools.base import ToolResult, register_tool


def _get_workspace(session=None) -> str:
    return getattr(session, "workspace_root", None) or "."


def request_memory_confirmation(
    title: str,
    content: str,
    scope: str = "library",
    kind: str = "profile_fact",
    target_item_id: str | None = None,
    session=None,
) -> ToolResult:
    """Prepare a confirmation artifact without writing long-term knowledge."""
    from service.memory_service import MemoryService

    service = MemoryService(_get_workspace(session))
    if service.contains_secret(f"{title}\n{content}"):
        return ToolResult(
            ok=False,
            content="内容包含密码、令牌、API 密钥或其他秘密，不能保存为个人知识。",
        )
    if scope not in {"global", "library"}:
        scope = "library"
    if kind not in {
        "preference", "goal", "profile_fact", "learning_strategy",
        "course_insight", "study_pattern",
    }:
        kind = "profile_fact"
    before = None
    if target_item_id:
        existing = service.get_knowledge(target_item_id)
        before = existing.get("item") if existing.get("ok") else None
        if not before:
            target_item_id = None
    artifact = {
        "type": "memory_confirmation",
        "artifact_id": uuid.uuid4().hex,
        "status": "pending",
        "scope": scope,
        "kind": kind,
        "title": title.strip()[:120] or "需要记住的内容",
        "content": content.strip()[:5000],
        "target_item_id": target_item_id,
        "before": before,
        "requires_warning": service.is_sensitive(f"{title}\n{content}"),
    }
    return ToolResult(
        ok=True,
        content="已向用户展示个人知识确认卡。用户确认前，不要声称内容已经保存。",
        artifacts=[artifact],
    )


register_tool(
    name="request_memory_confirmation",
    description=(
        "当用户明确要求记住长期有效的学习背景时，生成一张确认卡。"
        "本工具不会直接写入个人知识；设置项和秘密信息不应通过本工具保存。"
    ),
    params_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "简短、可读的个人知识标题"},
            "content": {"type": "string", "description": "等待用户确认的准确内容"},
            "scope": {"type": "string", "enum": ["global", "library"]},
            "kind": {
                "type": "string",
                "enum": ["preference", "goal", "profile_fact", "learning_strategy", "course_insight", "study_pattern"],
            },
            "target_item_id": {"type": "string", "description": "可选：要更新的个人知识 ID"},
        },
        "required": ["title", "content"],
    },
    func=request_memory_confirmation,
)
