import json
import os

from graph.store import get_graph_store

from .base import ToolResult, register_tool


def graph_query(concept: str, intent: str = "related", limit: int = 20, workspace: str = ".") -> ToolResult:
    """Query concept relationships from Neo4j or the local graph fallback."""
    store = get_graph_store(os.path.abspath(workspace))
    try:
        data = store.query(concept=concept, intent=intent, limit=max(1, min(int(limit), 50)))
    finally:
        if hasattr(store, "close"):
            store.close()

    return ToolResult(
        ok=True,
        content=json.dumps(data, ensure_ascii=False, indent=2),
        data=data,
    )


register_tool(
    "graph_query",
    "Query knowledge graph relationships for a concept. Supports intents like related, tags, mentions, course.",
    {
        "type": "object",
        "properties": {
            "concept": {"type": "string", "description": "Concept name to query"},
            "intent": {"type": "string", "description": "Query intent: related, tags, mentions, course, prerequisites"},
            "limit": {"type": "integer", "description": "Maximum relationship count, default 20"},
        },
        "required": ["concept"],
    },
    graph_query,
)
