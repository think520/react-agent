import inspect
import os
from dataclasses import dataclass, field
from typing import Callable, Any

TOOL_REGISTRY: dict[str, Callable] = {}
TOOL_SCHEMAS: list[dict] = []

# Files/dirs that tools refuse to read by default
DENY_READ_PATTERNS = {".env", ".env.", ".git", ".session", "__pycache__", ".venv", "venv"}

# Max file size for read_file (1 MB)
MAX_READ_SIZE = 1 * 1024 * 1024


@dataclass
class ToolResult:
    """Structured result from tool execution."""
    ok: bool
    content: str  # text sent to LLM
    data: dict = field(default_factory=dict)  # structured data for programmatic use


def _is_within_workspace(path: str, workspace: str) -> bool:
    """Check that resolved path is within workspace root."""
    resolved = os.path.realpath(path)
    workspace_real = os.path.realpath(workspace)
    return resolved.startswith(workspace_real + os.sep) or resolved == workspace_real


def _resolve_path(path: str, cwd: str) -> str:
    """Resolve relative tool paths against the current working directory."""
    return path if os.path.isabs(path) else os.path.abspath(os.path.join(cwd, path))


def _is_denied_path(path: str) -> bool:
    """Check if path matches a deny-list pattern."""
    basename = os.path.basename(path)
    for pattern in DENY_READ_PATTERNS:
        if pattern.endswith("."):
            # prefix match: ".env." matches ".env.local" etc.
            if basename.startswith(pattern):
                return True
        elif basename == pattern:
            return True
    return False


def _build_tool_schema(name: str, description: str, params_schema: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": params_schema,
        }
    }


def register_tool(name: str, description: str, params_schema: dict, func: Callable) -> None:
    """Register a tool with its schema."""
    TOOL_REGISTRY[name] = func
    schema = _build_tool_schema(name, description, params_schema)

    for index, existing in enumerate(TOOL_SCHEMAS):
        if existing.get("function", {}).get("name") == name:
            TOOL_SCHEMAS[index] = schema
            break
    else:
        TOOL_SCHEMAS.append(schema)


def get_tools_schema() -> list[dict]:
    """Return the combined tools schema for LLM."""
    return list(TOOL_SCHEMAS)


def execute_tool(name: str, args: dict, session=None) -> Any:
    """Execute a tool by name with given arguments.

    Returns ToolResult for registered tools, or error string for unknown tools.
    """
    if name not in TOOL_REGISTRY:
        return ToolResult(ok=False, content=f"Unknown tool: {name}")

    func = TOOL_REGISTRY[name]
    call_args = dict(args)

    try:
        sig = inspect.signature(func)
        if session is not None:
            if "cwd" in sig.parameters:
                call_args.setdefault("cwd", session.cwd)
            if "workspace" in sig.parameters:
                call_args.setdefault("workspace", session.workspace_root)
        result = func(**call_args)
        # Ensure result is a ToolResult
        if not isinstance(result, ToolResult):
            result = ToolResult(ok=True, content=str(result))
        return result
    except Exception as e:
        return ToolResult(ok=False, content=f"Tool execution error: {str(e)}")
