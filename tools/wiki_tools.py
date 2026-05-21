"""Agent tools for wiki ingest and lint."""

import os
import json
from tools.base import register_tool, ToolResult


def _get_workspace(session=None) -> str:
    return getattr(session, "workspace_root", None) or "."


def wiki_ingest(source_path: str, vault_path: str, force: bool = False,
                session=None) -> ToolResult:
    """Compile source files into wiki pages.

    Reads source documents, uses LLM to extract entities and concepts,
    and writes structured wiki pages to the Obsidian vault.
    """
    workspace = _get_workspace(session)

    # Resolve paths
    if not os.path.isabs(source_path):
        source_path = os.path.join(workspace, source_path)
    if not os.path.isabs(vault_path):
        vault_path = os.path.join(workspace, vault_path)

    if not os.path.exists(source_path):
        return ToolResult(ok=False, content=f"Source path not found: {source_path}")

    try:
        from wiki.compiler import WikiCompiler
        compiler = WikiCompiler(workspace, vault_path)

        # Collect source files
        source_files = []
        if os.path.isfile(source_path):
            source_files = [source_path]
        elif os.path.isdir(source_path):
            for root, dirs, files in os.walk(source_path):
                # Skip hidden dirs and wiki dir itself
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'wiki']
                for f in files:
                    if f.endswith(".md"):
                        source_files.append(os.path.join(root, f))

        if not source_files:
            return ToolResult(ok=False, content="No .md files found in source path")

        # Compile
        result = compiler.compile_batch(source_files, force=force)

        # Format summary
        lines = [f"Wiki 编译完成："]
        lines.append(f"  处理文件：{len(source_files)}")
        lines.append(f"  生成实体：{result.entities_count}")
        lines.append(f"  生成概念：{result.concepts_count}")
        lines.append(f"  生成来源页：{result.sources_count}")
        if result.skipped:
            lines.append(f"  跳过（未变更）：{len(result.skipped)}")
        if result.errors:
            lines.append(f"  错误：{len(result.errors)}")

        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={
                "entities": result.entities_count,
                "concepts": result.concepts_count,
                "sources": result.sources_count,
                "skipped": len(result.skipped),
                "errors": len(result.errors),
                "pages": [p.title for p in result.pages],
            },
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Wiki ingest failed: {e}")


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
    name="wiki_ingest",
    description="Compile source documents into structured wiki pages in the Obsidian vault. "
                "Uses LLM to extract entities, concepts, and summaries from source files. "
                "Supports incremental updates — only recompiles changed sources.",
    params_schema={
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path to source file or directory to compile",
            },
            "vault_path": {
                "type": "string",
                "description": "Path to Obsidian vault (wiki pages will be written to vault/wiki/)",
            },
            "force": {
                "type": "boolean",
                "description": "Force recompile even if sources haven't changed (default: false)",
            },
        },
        "required": ["source_path", "vault_path"],
    },
    func=wiki_ingest,
)

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
