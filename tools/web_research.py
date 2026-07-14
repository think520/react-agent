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
