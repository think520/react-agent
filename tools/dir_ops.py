import os
from .base import register_tool, ToolResult, _is_within_workspace, _resolve_path


def list_dir(path: str = ".", cwd: str = ".", workspace: str = ".") -> ToolResult:
    """List directory contents."""
    target_path = _resolve_path(path, cwd)

    if not _is_within_workspace(target_path, workspace):
        return ToolResult(ok=False, content=f"Access denied: {path} is outside workspace")

    try:
        if not os.path.exists(target_path):
            return ToolResult(ok=False, content=f"Directory not found: {path}")
        if not os.path.isdir(target_path):
            return ToolResult(ok=False, content=f"Not a directory: {path}")

        entries = os.listdir(target_path)
        if not entries:
            return ToolResult(ok=True, content="(empty directory)")

        result = []
        for entry in entries:
            full_path = os.path.join(target_path, entry)
            if os.path.isdir(full_path):
                result.append(f"[DIR] {entry}/")
            else:
                size = os.path.getsize(full_path)
                result.append(f"[FILE] {entry} ({size} bytes)")
        return ToolResult(ok=True, content="\n".join(result))
    except Exception as e:
        return ToolResult(ok=False, content=f"Error listing directory: {str(e)}")


def change_dir(path: str, cwd: str = ".", workspace: str = ".") -> ToolResult:
    """Change working directory. Returns the new absolute path."""
    target_path = _resolve_path(path, cwd)

    if not _is_within_workspace(target_path, workspace):
        return ToolResult(ok=False, content=f"Access denied: cannot leave workspace root")

    try:
        if not os.path.exists(target_path):
            return ToolResult(ok=False, content=f"Directory not found: {path}")
        if not os.path.isdir(target_path):
            return ToolResult(ok=False, content=f"Not a directory: {path}")

        abs_path = os.path.abspath(target_path)
        return ToolResult(
            ok=True,
            content=f"Changed directory: {abs_path}",
            data={"cwd": abs_path},
        )
    except Exception as e:
        return ToolResult(ok=False, content=f"Error changing directory: {str(e)}")


def stat_path(path: str, cwd: str = ".", workspace: str = ".") -> ToolResult:
    """Get file or directory info."""
    target_path = _resolve_path(path, cwd)

    if not _is_within_workspace(target_path, workspace):
        return ToolResult(ok=False, content=f"Access denied: {path} is outside workspace")

    try:
        if not os.path.exists(target_path):
            return ToolResult(ok=False, content=f"Path not found: {path}")

        stat = os.stat(target_path)
        is_dir = os.path.isdir(target_path)

        result = f"Type: {'directory' if is_dir else 'file'}\n"
        result += f"Path: {target_path}\n"
        result += f"Size: {stat.st_size} bytes\n"
        result += f"Created: {stat.st_ctime}\n"
        result += f"Modified: {stat.st_mtime}\n"

        return ToolResult(ok=True, content=result)
    except Exception as e:
        return ToolResult(ok=False, content=f"Error getting path info: {str(e)}")


# Register tools
register_tool(
    "list_dir",
    "List directory contents. Shows files and subdirectories.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path (default: current directory)"},
        },
        "required": []
    },
    list_dir
)

register_tool(
    "change_dir",
    "Change the working directory. Returns the new absolute path.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target directory path"},
        },
        "required": ["path"]
    },
    change_dir
)

register_tool(
    "stat_path",
    "Get file or directory metadata (type, size, timestamps).",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or directory path"},
        },
        "required": ["path"]
    },
    stat_path
)
