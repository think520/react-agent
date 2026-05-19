"""Agent tools for memory save and recall."""

from core.memory import MemoryManager
from tools.base import register_tool, ToolResult


def _get_memory_manager(session=None) -> MemoryManager:
    """Get a MemoryManager instance using the session's workspace root."""
    workspace = getattr(session, "workspace_root", None) or "."
    return MemoryManager(workspace)


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
    """Search saved memories by semantic similarity."""
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
            source = result.get("source", "").replace("memory://", "")
            score = result.get("score", 0)
            text = result.get("text", "")[:200]
            lines.append(f"{i}. [{source}] (score: {score:.3f}) {text}")

        return ToolResult(ok=True, content="\n".join(lines))
    except Exception as e:
        return ToolResult(ok=False, content=f"Error recalling memories: {e}")


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
    description="Search previously saved memories by semantic similarity. "
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
