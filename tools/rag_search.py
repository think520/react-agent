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
        _config_cache = ProviderFactory.load_config(
            os.getenv("BOBODAN_CONFIG", "config.yaml")
        )
    except Exception:
        _config_cache = {}
    return _config_cache


def rag_search(
    query: str,
    course: str | None = None,
    top_k: int = 5,
    mode: str = "auto",
    document_ids: list[str] | None = None,
    workspace: str = ".",
) -> ToolResult:
    """Search the workspace-local knowledge index."""
    try:
        from service.kb_service import KBService
        svc = KBService(workspace)
        config = _load_config()
        result = svc.search(
            query=query,
            course=course,
            top_k=top_k,
            mode=mode,
            document_ids=document_ids,
            config=config,
        )
        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"], data={"results": []})

        results = result["results"]
        data = {"results": results}
        sources = []
        for item in results:
            metadata = item.get("metadata") or {}
            source = str(item.get("source", ""))
            sources.append({
                "source_type": "local",
                "source_id": str(item.get("chunk_id") or source),
                "title": str(item.get("title") or metadata.get("title") or source),
                "document_id": item.get("document_id"),
                "chunk_id": item.get("chunk_id"),
                "heading": metadata.get("heading_text") or item.get("heading_text"),
                "page": metadata.get("page_start") or item.get("page_start"),
                "slide": metadata.get("slide_start") or item.get("slide_start"),
                "collection": item.get("collection", "material"),
            })

        artifacts = []
        if sources:
            artifacts.append({
                "type": "citation",
                "attribution": {"kind": "local", "sources": sources},
            })

        return ToolResult(
            ok=True,
            content=json.dumps(data, ensure_ascii=False, indent=2) + "\n\n" + format_search_results(results),
            data=data,
            artifacts=artifacts,
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error searching knowledge base: {e}")


register_tool(
    "rag_search",
    "Search course materials and Obsidian notes in the local RAG index. Returns source-grounded snippets. "
    "mode is optional: auto (default), hybrid (vector+FTS5), directory (document routing), directory_grep (exact source lookup).",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query or question"},
            "course": {"type": "string", "description": "Optional exact course filter"},
            "top_k": {"type": "integer", "description": "Maximum number of chunks to return, default 5"},
            "mode": {
                "type": "string",
                "description": "Retrieval mode: auto (default), hybrid, directory, directory_grep",
                "enum": ["auto", "hybrid", "directory", "directory_grep"],
            },
            "document_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional document IDs selected by the user as the active study scope",
            },
        },
        "required": ["query"],
    },
    rag_search,
)
