import json

from knowledge.library import format_library_summary

from .base import register_tool, ToolResult


def knowledge_status(workspace: str = ".") -> ToolResult:
    """Return detailed knowledge base status including courses, file counts,
    chunk counts, error files, and graph statistics."""
    try:
        from service.kb_service import KBService
        svc = KBService(workspace)
        result = svc.status()
        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"])

        # Build a summary object for format_library_summary
        from knowledge.library import LibrarySummary, CourseSummary
        summary = LibrarySummary(
            total_files=result["total_files"],
            total_chunks=result["total_chunks"],
            total_errors=result["total_errors"],
            graph_nodes=result["graph_nodes"],
            graph_relationships=result["graph_relationships"],
            graph_nodes_by_type=result.get("graph_nodes_by_type", {}),
            graph_relationships_by_type=result.get("graph_relationships_by_type", {}),
            graph_backend=result.get("graph_backend", "unknown"),
            last_sync=result.get("last_sync"),
            courses=[
                CourseSummary(
                    name=c["name"],
                    file_count=c["file_count"],
                    chunk_count=c["chunk_count"],
                    error_count=c["error_count"],
                )
                for c in result.get("courses", [])
            ],
        )

        return ToolResult(
            ok=True,
            content=format_library_summary(summary),
            data=result,
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Failed to get knowledge status: {e}")


register_tool(
    name="knowledge_status",
    description="Get detailed status of the local knowledge base: courses, file counts, chunk counts, error files, and knowledge graph statistics.",
    params_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
    func=knowledge_status,
)
