"""Agent tools for memory recall and user-confirmed memory proposals."""

import uuid

from tools.base import register_tool, ToolResult


def _get_workspace(session=None) -> str:
    return getattr(session, "workspace_root", None) or "."


def memory_save(name: str, description: str, content: str,
                entry_type: str = "user", session=None) -> ToolResult:
    """Save a persistent memory for future sessions."""
    try:
        from service.memory_service import MemoryService
        svc = MemoryService(_get_workspace(session))
        result = svc.save(name=name, description=description, content=content, entry_type=entry_type)
        if not result["ok"]:
            return ToolResult(ok=False, content=f"Error: {result['error']}")
        return ToolResult(
            ok=True,
            content=f"Memory saved: {result['name']} ({result['type']})",
            data={"name": result["name"], "type": result["type"]},
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error saving memory: {e}")


def memory_recall(query: str, top_k: int = 5, session=None) -> ToolResult:
    """Search saved memories by FTS5 keyword search with vector fallback."""
    try:
        from service.memory_service import MemoryService
        svc = MemoryService(_get_workspace(session))
        result = svc.recall(query=query, top_k=top_k)
        if not result["ok"]:
            return ToolResult(ok=False, content=f"Error: {result['error']}")

        if not result["results"]:
            fallback = result.get("fallback", [])
            if fallback:
                lines = ["No matching memories found. Here are all saved memories:"]
                for entry in fallback:
                    lines.append(f"- [{entry['type']}] {entry['name']}: {entry['description']}")
                return ToolResult(ok=True, content="\n".join(lines))
            return ToolResult(ok=True, content="No memories saved yet.")

        lines = [f"Found {len(result['results'])} relevant memories:"]
        for i, r in enumerate(result["results"], 1):
            method_tag = f" [{r['method']}]" if r["method"] else ""
            lines.append(f"{i}. [{r['source']}]{method_tag} (score: {r['score']:.3f}) {r['text']}")

        return ToolResult(ok=True, content="\n".join(lines))
    except Exception as e:
        return ToolResult(ok=False, content=f"Error recalling memories: {e}")


def memory_daily_save(content: str, tags: list[str] | None = None,
                      session=None) -> ToolResult:
    """Save content to today's daily memory file."""
    try:
        from service.memory_service import MemoryService
        svc = MemoryService(_get_workspace(session))
        result = svc.daily_save(content=content, tags=tags)
        if not result["ok"]:
            return ToolResult(ok=False, content=f"Error: {result['error']}")
        return ToolResult(
            ok=True,
            content=f"Daily memory saved to {result['path']}",
            data={"path": result["path"], "date": result["date"]},
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error saving daily memory: {e}")


def memory_daily_read(date: str | None = None, session=None) -> ToolResult:
    """Read a daily memory file. Defaults to today if no date given."""
    try:
        from service.memory_service import MemoryService
        svc = MemoryService(_get_workspace(session))
        result = svc.daily_read(date=date)
        if not result["ok"]:
            return ToolResult(ok=False, content=f"Error: {result['error']}")

        if not result["content"].strip():
            date_label = "today" if not date else date
            return ToolResult(ok=True, content=f"No daily memory for {date_label}.")

        return ToolResult(
            ok=True,
            content=result["content"],
            data={"date": result["date"]},
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error reading daily memory: {e}")


def request_memory_confirmation(
    title: str,
    content: str,
    scope: str = "library",
    kind: str = "profile_fact",
    target_item_id: str | None = None,
    session=None,
) -> ToolResult:
    """Prepare a memory proposal without writing long-term knowledge."""
    from service.memory_service import MemoryService

    service = MemoryService(_get_workspace(session))
    if service.contains_secret(f"{title}\n{content}"):
        return ToolResult(
            ok=False,
            content="This contains a password, token, API key, or other secret and cannot be remembered.",
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
        content=(
            "A memory confirmation card is visible to the user. "
            "Do not claim the information was saved until the user confirms it."
        ),
        artifacts=[artifact],
    )


register_tool(
    name="memory_save",
    description="Save a persistent memory about the user, their preferences, learning context, or feedback. "
                "Memories persist across sessions and help personalize future interactions. "
                "Use type 'user' for user profile/preferences, 'feedback' for corrections/confirmations, "
                "'project' for project context, 'reference' for external resource pointers.",
    params_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique identifier for this memory (e.g., 'learning-style', 'python-level')",
            },
            "description": {
                "type": "string",
                "description": "Brief one-line description of what this memory contains",
            },
            "content": {
                "type": "string",
                "description": "The actual memory content to save",
            },
            "entry_type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "Category of this memory (default: user)",
            },
        },
        "required": ["name", "description", "content"],
    },
    func=memory_save,
)

register_tool(
    name="memory_recall",
    description="Search previously saved memories by FTS5 keyword search with vector fallback. "
                "Use this to recall user preferences, past feedback, or project context "
                "before answering questions that might benefit from remembered information.",
    params_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language query to search memories",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5)",
            },
        },
        "required": ["query"],
    },
    func=memory_recall,
)

register_tool(
    name="memory_daily_save",
    description="Save content to today's daily memory file. "
                "Daily memories are short-lived notes that can later be promoted to permanent memory. "
                "Use this after quiz sessions, learning activities, or when the user says 'remember this'.",
    params_schema={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Content to save to today's daily memory",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for categorization (e.g., ['quiz', 'regex', 'learning'])",
            },
        },
        "required": ["content"],
    },
    func=memory_daily_save,
)

register_tool(
    name="memory_daily_read",
    description="Read a daily memory file. Defaults to today if no date given. "
                "Useful for reviewing what was learned on a specific day.",
    params_schema={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format. Defaults to today UTC.",
            },
        },
        "required": [],
    },
    func=memory_daily_read,
)

register_tool(
    name="request_memory_confirmation",
    description=(
        "Prepare a confirmation card when the user explicitly asks Bobodan to remember durable learning context. "
        "This tool does not write memory. Do not use it for display name, teaching style, answer depth, feedback strength, "
        "or configured long-term goal; those use settings. Never propose passwords, tokens, API keys, or secrets."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short user-readable memory title"},
            "content": {"type": "string", "description": "The exact durable fact or preference to confirm"},
            "scope": {"type": "string", "enum": ["global", "library"]},
            "kind": {
                "type": "string",
                "enum": ["preference", "goal", "profile_fact", "learning_strategy", "course_insight", "study_pattern"],
            },
            "target_item_id": {"type": "string", "description": "Optional confirmed knowledge item to update"},
        },
        "required": ["title", "content"],
    },
    func=request_memory_confirmation,
)
