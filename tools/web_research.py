from __future__ import annotations

import uuid

from .base import ToolResult, register_tool


def request_web_search(query: str, reason: str = "本地资料不足，需要补充公开网页来源。") -> ToolResult:
    artifact = {
        "type": "web_consent",
        "artifact_id": uuid.uuid4().hex,
        "status": "pending",
        "query": query.strip(),
        "reason": reason.strip(),
    }
    return ToolResult(
        ok=True,
        content="Web search requires the user's confirmation. Wait for the user to approve the request.",
        data={"requested": True},
        artifacts=[artifact],
    )


def web_research(
    query: str,
    workspace: str = ".",
    search_provider: str = "auto",
    jina_fallback: bool = True,
    research_session_id: str | None = None,
) -> ToolResult:
    from service.research_service import ResearchService

    session_id = research_session_id or f"agent-{uuid.uuid4().hex}"
    result = ResearchService(workspace).auto_research(
        session_id,
        query,
        provider_name=search_provider,
        jina_fallback=jina_fallback,
    )
    if not result["sources"]:
        return ToolResult(
            ok=False,
            content="No selected web page returned readable evidence. Continue without web claims or explain the limitation.",
            data={"web_research_id": result["research_id"]},
        )
    candidates_artifact = {
        "type": "web_candidates",
        "artifact_id": uuid.uuid4().hex,
        "search_id": result["search_id"],
        "status": "used",
        "query": result["query"],
        "provider": result["provider"],
        "selected_candidate_ids": result["selected_candidate_ids"],
        "candidates": [
            {
                "candidate_id": item["candidate_id"],
                "title": item["title"],
                "url": item["url"],
                "domain": item["domain"],
                "snippet": item.get("snippet", ""),
                "published_at": item.get("published_at"),
                "rank": item.get("rank", 0),
                "provider": item["provider"],
                "quality_hint": item["quality_hint"],
            }
            for item in result["candidates"]
        ],
    }
    evidence_artifact = {
        "type": "web_evidence",
        "artifact_id": uuid.uuid4().hex,
        "research_id": result["research_id"],
        "status": result["status"],
        "sources": result["sources"],
        "failed_source_ids": result["failed_source_ids"],
    }
    citation_artifact = {
        "type": "citation",
        "attribution": {"kind": "web", "sources": result["sources"]},
    }
    return ToolResult(
        ok=True,
        content=(
            "The following text comes from immutable web evidence snapshots selected by Bobodan. "
            "Search snippets are not evidence. Cite the attached sources for web-grounded claims.\n\n"
            + result["content"]
        ),
        data={"web_research_id": result["research_id"]},
        artifacts=[candidates_artifact, evidence_artifact, citation_artifact],
    )


register_tool(
    "request_web_search",
    "Ask the user for permission to search public web sources. This tool never accesses the network. "
    "Use it only when local sources are insufficient; after calling it, briefly explain the gap and wait.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "A concise search query"},
            "reason": {"type": "string", "description": "Why local evidence is insufficient"},
        },
        "required": ["query"],
    },
    request_web_search,
)

register_tool(
    "web_research",
    "Search and read trusted public web sources when current local evidence is insufficient or current information is required. "
    "This tool is available only when the user has enabled automatic web research. It returns page evidence, not search snippets.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "A concise search query"},
        },
        "required": ["query"],
    },
    web_research,
)
