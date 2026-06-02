import json
import os

from rag.citations import format_search_results
from rag.retriever import search_index

from .base import ToolResult, register_tool

_config_cache = None


def _load_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        from providers.factory import ProviderFactory
        _config_cache = ProviderFactory.load_config("config.yaml")
    except Exception:
        _config_cache = {}
    return _config_cache


def rag_search(query: str, course: str | None = None, top_k: int = 5, workspace: str = ".") -> ToolResult:
    """Search the workspace-local knowledge index."""
    knowledge_dir = os.path.join(workspace, ".knowledge")
    sparse_path = os.path.join(knowledge_dir, "rag_index.json")
    dense_path = os.path.join(knowledge_dir, "rag_index_dense.json")
    if not os.path.exists(sparse_path) and not os.path.exists(dense_path):
        return ToolResult(
            ok=False,
            content="RAG index not found. Run obsidian_sync first.",
            data={"results": []},
        )

    config = _load_config()
    results = search_index(os.path.abspath(workspace), query=query, course=course, top_k=top_k, config=config)
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
