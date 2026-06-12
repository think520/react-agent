import json
import os

from rag.citations import format_search_results

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
    try:
        from service.kb_service import KBService
        svc = KBService(workspace)
        config = _load_config()
        result = svc.search(query=query, course=course, top_k=top_k, config=config)
        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"], data={"results": []})

        results = result["results"]
        data = {"results": results}
        return ToolResult(
            ok=True,
            content=json.dumps(data, ensure_ascii=False, indent=2) + "\n\n" + format_search_results(results),
            data=data,
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error searching knowledge base: {e}")


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
