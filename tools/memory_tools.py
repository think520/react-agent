"""Agent tools for memory save, recall, daily memory, and promotion."""

import logging

from tools.base import register_tool, ToolResult

logger = logging.getLogger(__name__)


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


def memory_promote(dry_run: bool = False, session=None) -> ToolResult:
    """Check and execute promotion of daily memories to permanent memory."""
    try:
        from service.memory_service import MemoryService
        svc = MemoryService(_get_workspace(session))
        result = svc.promote(dry_run=dry_run)

        candidates = result["candidates"]
        if not candidates:
            return ToolResult(ok=True, content="No daily memories are ready for promotion yet.")

        lines = [f"Found {len(candidates)} daily memory candidates:\n"]
        for c in candidates:
            status = "✓ eligible" if c["eligible"] else "✗ not ready"
            lines.append(
                f"  {c['date']} — score: {c['score']:.2f} "
                f"(freq={c['frequency']:.1f}, quiz={c['quiz']:.1f}, recency={c['recency']:.1f}) "
                f"recalls={c['recall_count']} — {status}"
            )
            if c.get("promoted"):
                lines.append(f"    → {c['details']}")

        if dry_run:
            lines.append("\n(Dry run — no memories were promoted)")
        elif result["promoted"] > 0:
            lines.append(f"\nPromoted {result['promoted']} daily memories to permanent.")
        else:
            lines.append("\nNo memories met the promotion threshold (score ≥ 0.6, recalls ≥ 2).")

        return ToolResult(ok=True, content="\n".join(lines), data={
            "candidates": len(candidates), "promoted": result["promoted"],
        })
    except Exception as e:
        return ToolResult(ok=False, content=f"Error checking promotions: {e}")


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
    name="memory_promote",
    description="Check and promote daily memories to permanent memory. "
                "Promotes memories that have been recalled frequently, are related to quiz performance, "
                "and are at least 3 days old. Use dry_run=true to preview without promoting.",
    params_schema={
        "type": "object",
        "properties": {
            "dry_run": {
                "type": "boolean",
                "description": "If true, only show candidates without promoting (default: false)",
            },
        },
        "required": [],
    },
    func=memory_promote,
)
