import json
import os

from rag.citations import format_search_results
from rag.retriever import search_index

from .base import ToolResult, register_tool


def rag_search(query: str, course: str | None = None, top_k: int = 5, workspace: str = ".") -> ToolResult:
    """Search the workspace-local knowledge index."""
    index_path = os.path.join(workspace, ".knowledge", "rag_index.json")
    if not os.path.exists(index_path):
        return ToolResult(
            ok=False,
            content="RAG index not found. Run obsidian_sync first.",
            data={"results": []},
        )

    results = search_index(os.path.abspath(workspace), query=query, course=course, top_k=top_k)
    data = {"results": results}
    return ToolResult(
        ok=True,
        content=json.dumps(data, ensure_ascii=False, indent=2) + "\n\n" + format_search_results(results),
        data=data,
    )


register_tool(
    "rag_search",
    "Search course materials and Obsidian notes in the local RAG index. Returns source-grounded snippets.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query or question"},
            "course": {"type": "string", "description": "Optional exact course filter"},
            "top_k": {"type": "integer", "description": "Maximum number of chunks to return, default 5"},
        },
        "required": ["query"],
    },
    rag_search,
)
