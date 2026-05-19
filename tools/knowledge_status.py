import json
import os

from knowledge.library import build_library_summary, format_library_summary
from knowledge.import_report import load_import_report

from .base import register_tool, ToolResult


def knowledge_status(workspace: str = ".") -> ToolResult:
    """Return detailed knowledge base status including courses, file counts,
    chunk counts, error files, and graph statistics."""
    try:
        knowledge_dir = os.path.join(workspace, ".knowledge")
        if not os.path.exists(knowledge_dir):
            return ToolResult(ok=False, content="No knowledge base found. Run obsidian_sync first.")

        summary = build_library_summary(workspace)
        report = load_import_report(workspace)

        result = {
            "total_files": summary.total_files,
            "total_chunks": summary.total_chunks,
            "total_errors": summary.total_errors,
            "graph_nodes": summary.graph_nodes,
            "graph_relationships": summary.graph_relationships,
            "graph_nodes_by_type": summary.graph_nodes_by_type,
            "graph_relationships_by_type": summary.graph_relationships_by_type,
            "graph_backend": summary.graph_backend,
            "last_sync": summary.last_sync,
            "courses": [
                {
                    "name": cs.name,
                    "file_count": cs.file_count,
                    "chunk_count": cs.chunk_count,
                    "error_count": cs.error_count,
                }
                for cs in summary.courses
            ],
        }

        if report:
            result["last_import"] = {
                "timestamp": report.timestamp,
                "mode": report.mode,
                "error_files": report.error_files,
                "errors": report.errors[:10],
            }

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
