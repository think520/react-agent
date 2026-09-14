import inspect
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Any

logger = logging.getLogger(__name__)

TOOL_REGISTRY: dict[str, Callable] = {}
TOOL_SCHEMAS: list[dict] = []

# Files that tools refuse to touch, matched on the basename.
DENY_READ_PATTERNS = {".env", ".env.", ".git", ".session", "__pycache__", ".venv", "venv"}

# P0-6: directories that are internal to the app (or to version control) and
# must not be reachable through the tools. Matched on path *segments* below the
# workspace, because a basename match let `.git/config`, `.knowledge/knowledge.db`
# and `.session/<id>.json` through — their basenames look innocent.
DENY_PATH_SEGMENTS = (".git", ".session", ".knowledge", ".bobodan", "__pycache__", ".venv", "venv", "node_modules")
_DENY_SEGMENTS_CASEFOLD = frozenset(segment.casefold() for segment in DENY_PATH_SEGMENTS)

# Max file size for read_file (1 MB)
MAX_READ_SIZE = 1 * 1024 * 1024


@dataclass
class ToolResult:
    """Structured result from tool execution."""
    ok: bool
    content: str  # text sent to LLM
    data: dict = field(default_factory=dict)  # structured data for programmatic use
    artifacts: list[dict] = field(default_factory=list)  # safe structured data for UIs
    # E4: when set, the chat loop ends this turn after dispatching the tool, and
    # the run resumes once the user answers. Shape mirrors the ask_user artifact.
    pause_for_user: dict | None = None


def _is_within_workspace(path: str, workspace: str) -> bool:
    """Check that resolved path is within workspace root.

    P2-2: compare case-insensitively on Windows (`os.path.normcase` is a no-op
    elsewhere), where `C:\\Foo` and `c:\\foo` are the same file.
    """
    resolved = os.path.normcase(os.path.realpath(path))
    workspace_real = os.path.normcase(os.path.realpath(workspace))
    return resolved == workspace_real or resolved.startswith(workspace_real.rstrip(os.sep) + os.sep)


def _resolve_path(path: str, cwd: str) -> str:
    """Resolve relative tool paths against the current working directory."""
    return path if os.path.isabs(path) else os.path.abspath(os.path.join(cwd, path))


def _is_denied_path(path: str, workspace: str | None = None) -> bool:
    """True when the path names a protected file or lives in a protected directory.

    P0-6: the basename check alone let internal directories through. Directory
    segments are only inspected *below* the workspace, so a workspace that
    merely sits under a directory named `venv` still works.
    """
    basename = os.path.basename(path)
    for pattern in DENY_READ_PATTERNS:
        if pattern.endswith("."):
            # prefix match: ".env." matches ".env.local" etc.
            if basename.startswith(pattern):
                return True
        elif basename == pattern:
            return True

    relative = path
    if workspace:
        try:
            candidate = os.path.relpath(path, workspace)
        except ValueError:  # different drive on Windows
            candidate = path
        if not candidate.startswith(".."):
            relative = candidate
    for segment in os.path.normcase(relative).replace("\\", "/").split("/"):
        if segment and segment.casefold() in _DENY_SEGMENTS_CASEFOLD:
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

    try:
        sig = inspect.signature(func)
        # P0-5: a tool receives only the parameters it declares. The model used
        # to be able to smuggle in `workspace` / `cwd` / `chat_session_id` and
        # pick its own sandbox root, because every arg was passed straight
        # through. Session-scoped values below are assigned, not defaulted, so a
        # model-supplied value can never win.
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in sig.parameters.values()
        )
        declared = {
            parameter_name
            for parameter_name, parameter in sig.parameters.items()
            if parameter.kind
            in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        call_args = {
            key: value
            for key, value in args.items()
            if accepts_kwargs or key in declared
        }
        if session is not None:
            if "cwd" in sig.parameters:
                call_args["cwd"] = session.cwd
            if "workspace" in sig.parameters:
                call_args["workspace"] = session.workspace_root
            if "document_ids" in sig.parameters and hasattr(session, "active_document_ids"):
                call_args["document_ids"] = getattr(session, "active_document_ids")
            if "preferred_document_ids" in sig.parameters and hasattr(session, "preferred_document_ids"):
                call_args["preferred_document_ids"] = getattr(session, "preferred_document_ids")
            if "web_research_id" in sig.parameters:
                call_args["web_research_id"] = getattr(session, "active_web_research_id", None)
            if "search_provider" in sig.parameters:
                call_args["search_provider"] = getattr(session, "search_provider", "auto")
            if "jina_fallback" in sig.parameters:
                call_args["jina_fallback"] = getattr(session, "jina_fallback", True)
            if "research_session_id" in sig.parameters:
                call_args["research_session_id"] = session.session_id
            if "chat_session_id" in sig.parameters:
                call_args["chat_session_id"] = session.session_id
        result = func(**call_args)
        # Ensure result is a ToolResult
        if not isinstance(result, ToolResult):
            result = ToolResult(ok=True, content=str(result))
        return result
    except Exception as e:
        logger.exception("Tool %s raised an unexpected exception", name)
        return ToolResult(ok=False, content=f"Tool execution error: {str(e)}")
