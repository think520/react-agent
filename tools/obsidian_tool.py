import json
import os

from obsidian.sync import sync_sources

from .base import ToolResult, _is_within_workspace, _resolve_path, register_tool


def obsidian_sync(
    vault_path: str,
    course_dir: str | None = None,
    mode: str = "incremental",
    cwd: str = ".",
    workspace: str = ".",
) -> ToolResult:
    """Sync Obsidian Markdown and optional course documents into local RAG/graph stores."""
    if mode not in {"incremental", "full"}:
        return ToolResult(ok=False, content="mode must be either 'incremental' or 'full'")

    resolved_vault = _resolve_path(vault_path, cwd)
    if not _is_within_workspace(resolved_vault, workspace):
        return ToolResult(ok=False, content=f"Access denied: {vault_path} is outside workspace")
    if not os.path.isdir(resolved_vault):
        return ToolResult(ok=False, content=f"Vault directory not found: {vault_path}")

    resolved_course = None
    if course_dir:
        resolved_course = _resolve_path(course_dir, cwd)
        if not _is_within_workspace(resolved_course, workspace):
            return ToolResult(ok=False, content=f"Access denied: {course_dir} is outside workspace")
        if not os.path.isdir(resolved_course):
            return ToolResult(ok=False, content=f"Course directory not found: {course_dir}")

    summary = sync_sources(
        workspace=os.path.abspath(workspace),
        vault_path=resolved_vault,
        course_dir=resolved_course,
        mode=mode,
    )
    data = summary.to_dict()
    return ToolResult(
        ok=True,
        content=json.dumps(data, ensure_ascii=False, indent=2),
        data=data,
    )


register_tool(
    "obsidian_sync",
    "Scan an Obsidian vault and optional course document directory into the local RAG index and graph store.",
    {
        "type": "object",
        "properties": {
            "vault_path": {"type": "string", "description": "Obsidian vault path, relative to cwd or absolute within workspace"},
            "course_dir": {"type": "string", "description": "Optional course document directory with md/txt/pdf files"},
            "mode": {"type": "string", "description": "Sync mode: incremental or full, default incremental"},
        },
        "required": ["vault_path"],
    },
    obsidian_sync,
)
