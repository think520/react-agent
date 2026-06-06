import os
from .base import register_tool, ToolResult, _is_within_workspace, _is_denied_path, _resolve_path, MAX_READ_SIZE


def _is_binary(path: str, sample_size: int = 8192) -> bool:
    """Detect binary file by reading a sample and checking for null bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
            return b"\x00" in chunk
    except Exception:
        return False


def read_file(path: str, cwd: str = ".", workspace: str = ".") -> ToolResult:
    """Read a file. Paths are resolved relative to cwd, restricted to workspace."""
    target_path = _resolve_path(path, cwd)

    if not _is_within_workspace(target_path, workspace):
        return ToolResult(ok=False, content=f"Access denied: {path} is outside workspace")

    if _is_denied_path(target_path):
        return ToolResult(ok=False, content=f"Access denied: {path} is a protected file")

    try:
        if not os.path.exists(target_path):
            return ToolResult(ok=False, content=f"File not found: {path}")

        size = os.path.getsize(target_path)
        if size > MAX_READ_SIZE:
            return ToolResult(
                ok=False,
                content=f"File too large: {size} bytes (limit {MAX_READ_SIZE})",
            )

        if _is_binary(target_path):
            return ToolResult(ok=False, content=f"Binary file detected: {path}")

        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        return ToolResult(ok=True, content=content)
    except Exception as e:
        return ToolResult(ok=False, content=f"Error reading file: {str(e)}")


def write_file(path: str, content: str, cwd: str = ".",
               workspace: str = ".", overwrite: bool = False) -> ToolResult:
    """Write content to a file. Paths are resolved relative to cwd, restricted to workspace."""
    target_path = _resolve_path(path, cwd)

    if not _is_within_workspace(target_path, workspace):
        return ToolResult(ok=False, content=f"Access denied: {path} is outside workspace")

    if _is_denied_path(target_path):
        return ToolResult(ok=False, content=f"Access denied: {path} is a protected file")

    try:
        if os.path.exists(target_path) and not overwrite:
            return ToolResult(
                ok=False,
                content=f"File already exists: {path}. Pass overwrite=true to replace it.",
            )

        directory = os.path.dirname(target_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResult(ok=True, content=f"File written: {path}", data={"path": target_path})
    except Exception as e:
        return ToolResult(ok=False, content=f"Error writing file: {str(e)}")


# Register tools
register_tool(
    "read_file",
    "Read a file and return raw text. For read-and-summarize tasks, prefer delegate_doc_reader to isolate context.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path (relative to cwd or absolute)"},
        },
        "required": ["path"]
    },
    read_file
)

register_tool(
    "write_file",
    "Write content to a file. Creates parent directories if needed. Fails if file exists unless overwrite=true.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path (relative to cwd or absolute)"},
            "content": {"type": "string", "description": "Content to write"},
            "overwrite": {"type": "boolean", "description": "Allow overwriting existing file (default false)"},
        },
        "required": ["path", "content"]
    },
    write_file
)
