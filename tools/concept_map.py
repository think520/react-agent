import json
import uuid

from .base import ToolResult, register_tool


def concept_map_status(workspace: str = ".") -> ToolResult:
    """Return lightweight status for the reviewed concept map."""
    try:
        from service.concept_service import ConceptService

        result = ConceptService(workspace).get_status()
        if not result.get("ok"):
            return ToolResult(ok=False, content=str(result.get("error") or "status_failed"))
        data = {key: value for key, value in result.items() if key != "ok"}
        return ToolResult(
            ok=True,
            content=json.dumps(data, ensure_ascii=False, indent=2),
            data=data,
        )
    except Exception as exc:
        return ToolResult(ok=False, content=f"Failed to read concept map status: {exc}")


def concept_map_query(
    operation: str,
    query: str | None = None,
    concept_id: str | None = None,
    concept: str | None = None,
    target_concept_id: str | None = None,
    target_concept: str | None = None,
    depth: int = 1,
    limit: int = 20,
    workspace: str = ".",
) -> ToolResult:
    """Query reviewed concepts and relationships from the user-facing map."""
    try:
        from service.concept_service import ConceptService

        service = ConceptService(workspace)
        if operation == "search":
            result = service.search(query or concept or "", limit=limit)
        elif operation == "neighbors":
            result = service.neighbors(
                concept_id=concept_id,
                concept=concept or query,
                depth=depth,
                limit=limit,
            )
        elif operation == "path":
            result = service.path(
                from_concept_id=concept_id,
                from_concept=concept or query,
                to_concept_id=target_concept_id,
                to_concept=target_concept,
            )
        else:
            return ToolResult(ok=False, content=f"Unsupported operation: {operation}")

        if not result.get("ok"):
            data = {key: value for key, value in result.items() if key != "ok"}
            return ToolResult(
                ok=False,
                content=json.dumps(data, ensure_ascii=False, indent=2),
                data=data,
            )
        data = {key: value for key, value in result.items() if key != "ok"}
        # 空结果（如概念图里没有匹配概念）不输出「概念关系」卡片，
        # 避免渲染只有标题的空卡片。
        artifacts = []
        if data.get("concepts"):
            artifacts.append({
                "artifact_id": f"knowledge-{uuid.uuid4().hex[:12]}",
                "type": "knowledge_context",
                "context": data,
            })
        return ToolResult(
            ok=True,
            content=json.dumps(data, ensure_ascii=False, indent=2),
            data=data,
            artifacts=artifacts,
        )
    except Exception as exc:
        return ToolResult(ok=False, content=f"Error querying concept map: {exc}")


register_tool(
    "concept_map_status",
    "Get lightweight status for the reviewed concept map, including reviewed concept and relationship counts. Pending candidates are reported only as a count.",
    {
        "type": "object",
        "properties": {},
        "required": [],
    },
    concept_map_status,
)


register_tool(
    "concept_map_query",
    "Query the user's reviewed concept map. Use search to resolve concepts, neighbors for one- or two-hop reviewed relationships, and path for the shortest reviewed relationship path. Candidate concepts are never returned.",
    {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["search", "neighbors", "path"],
            },
            "query": {
                "type": "string",
                "description": "Search text or source concept name.",
            },
            "concept_id": {
                "type": "string",
                "description": "Optional exact source concept ID.",
            },
            "concept": {
                "type": "string",
                "description": "Optional exact source concept name.",
            },
            "target_concept_id": {
                "type": "string",
                "description": "Target concept ID for path queries.",
            },
            "target_concept": {
                "type": "string",
                "description": "Target concept name for path queries.",
            },
            "depth": {
                "type": "integer",
                "enum": [1, 2],
                "description": "Neighbor depth, limited to one or two hops.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum result count, capped by the service.",
            },
        },
        "required": ["operation"],
    },
    concept_map_query,
)
