"""Agent tools for memory save, recall, daily memory, and promotion."""

from core.memory import MemoryManager
from tools.base import register_tool, ToolResult


def _get_memory_manager(session=None) -> MemoryManager:
    """Get a MemoryManager instance using the session's workspace root."""
    workspace = getattr(session, "workspace_root", None) or "."
    return MemoryManager(workspace)


def _get_workspace(session=None) -> str:
    return getattr(session, "workspace_root", None) or "."


def memory_save(name: str, description: str, content: str,
                entry_type: str = "user", session=None) -> ToolResult:
    """Save a persistent memory for future sessions."""
    if not name or not name.strip():
        return ToolResult(ok=False, content="Error: name is required")
    if not content or not content.strip():
        return ToolResult(ok=False, content="Error: content is required")

    valid_types = {"user", "feedback", "project", "reference"}
    if entry_type not in valid_types:
        entry_type = "user"

    try:
        manager = _get_memory_manager(session)
        entry = manager.save(
            name=name.strip(),
            description=description.strip() if description else "",
            content=content.strip(),
            entry_type=entry_type,
        )
        return ToolResult(
            ok=True,
            content=f"Memory saved: {entry.name} ({entry.type})",
            data={"name": entry.name, "type": entry.type},
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error saving memory: {e}")


def memory_recall(query: str, top_k: int = 5, session=None) -> ToolResult:
    """Search saved memories by FTS5 keyword search with vector fallback."""
    if not query or not query.strip():
        return ToolResult(ok=False, content="Error: query is required")

    try:
        manager = _get_memory_manager(session)
        results = manager.search(query.strip(), top_k=max(1, min(top_k, 10)))

        if not results:
            # Fall back to listing all memories
            entries = manager.list_entries()
            if entries:
                lines = ["No matching memories found. Here are all saved memories:"]
                for entry in entries:
                    lines.append(f"- [{entry.type}] {entry.name}: {entry.description}")
                return ToolResult(ok=True, content="\n".join(lines))
            return ToolResult(ok=True, content="No memories saved yet.")

        lines = [f"Found {len(results)} relevant memories:"]
        for i, result in enumerate(results, 1):
            source = result.get("source", "").replace("memory://", "").replace("permanent://", "")
            score = result.get("score", 0)
            text = result.get("text", "")[:200]
            method = result.get("metadata", {}).get("method", "")
            method_tag = f" [{method}]" if method else ""
            lines.append(f"{i}. [{source}]{method_tag} (score: {score:.3f}) {text}")

        return ToolResult(ok=True, content="\n".join(lines))
    except Exception as e:
        return ToolResult(ok=False, content=f"Error recalling memories: {e}")


def memory_daily_save(content: str, tags: list[str] | None = None,
                      session=None) -> ToolResult:
    """Save content to today's daily memory file."""
    if not content or not content.strip():
        return ToolResult(ok=False, content="Error: content is required")

    try:
        from memory.daily import DailyMemoryManager
        workspace = _get_workspace(session)
        daily = DailyMemoryManager(workspace)
        filepath = daily.append(content.strip(), tags=tags)

        # Also index in FTS5
        try:
            from memory.store import MemoryIndexStore
            import datetime as dt
            today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            idx = MemoryIndexStore(workspace)
            idx.index_text(
                path=filepath,
                source="daily",
                text=content.strip(),
                date=today,
            )
        except Exception:
            pass  # FTS indexing is best-effort

        return ToolResult(
            ok=True,
            content=f"Daily memory saved to {filepath}",
            data={"path": filepath, "date": daily._today_str()},
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error saving daily memory: {e}")


def memory_daily_read(date: str | None = None, session=None) -> ToolResult:
    """Read a daily memory file. Defaults to today if no date given."""
    try:
        from memory.daily import DailyMemoryManager
        workspace = _get_workspace(session)
        daily = DailyMemoryManager(workspace)

        if not date:
            content = daily.get_today()
            date_label = "today"
        else:
            content = daily.read(date)
            date_label = date

        if not content.strip():
            return ToolResult(ok=True, content=f"No daily memory for {date_label}.")

        return ToolResult(
            ok=True,
            content=content,
            data={"date": date or daily._today_str()},
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error reading daily memory: {e}")


def memory_promote(dry_run: bool = False, session=None) -> ToolResult:
    """Check and execute promotion of daily memories to permanent memory.

    If dry_run=True, only shows candidates without promoting.
    """
    try:
        from memory.promotion import PromotionEngine
        workspace = _get_workspace(session)
        engine = PromotionEngine(workspace)

        candidates = engine.run_promotion_check()

        if not candidates:
            return ToolResult(ok=True, content="No daily memories are ready for promotion yet.")

        lines = [f"Found {len(candidates)} daily memory candidates:\n"]

        promoted_count = 0
        for c in candidates:
            status = "✓ eligible" if c["eligible"] else "✗ not ready"
            lines.append(
                f"  {c['date']} — score: {c['score']:.2f} "
                f"(freq={c['frequency']:.1f}, quiz={c['quiz']:.1f}, recency={c['recency']:.1f}) "
                f"recalls={c['recall_count']} — {status}"
            )

            if c["eligible"] and not dry_run:
                result = engine.promote(c["path"])
                if result["promoted"]:
                    promoted_count += 1
                    lines.append(f"    → {result['details']}")

        if dry_run:
            lines.append("\n(Dry run — no memories were promoted)")
        elif promoted_count > 0:
            lines.append(f"\nPromoted {promoted_count} daily memories to permanent.")
        else:
            lines.append("\nNo memories met the promotion threshold (score ≥ 0.6, recalls ≥ 2).")

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={"candidates": len(candidates), "promoted": promoted_count},
        )
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
