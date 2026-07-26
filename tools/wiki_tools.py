"""Agent tool for read-only Wiki health checks."""

import os
from tools.base import register_tool, ToolResult


def _get_workspace(session=None) -> str:
    return getattr(session, "workspace_root", None) or "."


def wiki_lint(vault_path: str, session=None) -> ToolResult:
    """Check wiki health: orphans, broken links, missing pages, staleness."""
    workspace = _get_workspace(session)

    if not os.path.isabs(vault_path):
        vault_path = os.path.join(workspace, vault_path)

    try:
        from wiki.lint import WikiLinter
        linter = WikiLinter(vault_path)
        result = linter.lint()
        summary = linter.format_result(result)

        return ToolResult(
            ok=True,
            content=summary,
            data={
                "total_pages": result.total_pages,
                "orphans": len(result.orphan_pages),
                "broken_links": len(result.broken_links),
                "missing": len(result.missing_pages),
                "stale": len(result.stale_pages),
                "healthy": result.healthy,
            },
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Wiki lint failed: {e}")


register_tool(
    name="wiki_lint",
    description="Check wiki health: find orphan pages, broken links, missing pages, and stale content.",
    params_schema={
        "type": "object",
        "properties": {
            "vault_path": {
                "type": "string",
                "description": "Path to Obsidian vault",
            },
        },
        "required": ["vault_path"],
    },
    func=wiki_lint,
)
