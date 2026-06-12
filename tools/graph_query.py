import json

from .base import ToolResult, register_tool


def graph_query(concept: str, intent: str = "related", limit: int = 20, workspace: str = ".") -> ToolResult:
    """Query concept relationships from Neo4j or the local graph fallback."""
    try:
        from service.kb_service import KBService
        svc = KBService(workspace)
        result = svc.graph_query(concept=concept, intent=intent, limit=limit)
        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"])

        data = {k: v for k, v in result.items() if k != "ok"}
        return ToolResult(
            ok=True,
            content=json.dumps(data, ensure_ascii=False, indent=2),
            data=data,
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error querying graph: {e}")


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
