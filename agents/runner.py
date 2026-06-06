"""Specialist runner — execute a specialist sub-AgentLoop in isolation.

This module owns:
  - fresh session construction (no parent messages, same cwd/workspace)
  - tool filtering (hard drop delegate_*, memory_*; default deny MCP)
  - sub-provider creation (capped timeout)
  - timeout enforcement via ThreadPoolExecutor
  - guarded catch (no auto-retry)
  - triage-specific contract validation
  - invocation record writing
  - content cap (2000 chars specialist output, 500 chars error)
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any

from core.agent_loop import AgentLoop
from core.session import Session
from tools.base import ToolResult, get_tools_schema

from .config import SpecialistConfig
from .prompt import render_specialist_prompt
from .registry import SpecialistRegistry

logger = logging.getLogger(__name__)

CONTENT_CAP_SPECIALIST = 2000
CONTENT_CAP_ERROR = 500
_TRUNCATION_NOTICE = "\n[...truncated; full result in data.result]"

# Hard filter prefixes — these are NEVER exposed to specialists in v1.
_HARD_DENY_PREFIXES = ("delegate_", "memory_")


# --- Tool filtering (Invariants 1, 2, 3, 4) ---


def build_specialist_tools(cfg: SpecialistConfig, all_tools: list[dict]) -> list[dict]:
    """Build the effective tool list for one specialist invocation.

    Hard deny delegate_* and memory_* (Invariants 1, 2). Default deny
    MCP unless allow_mcp=true (Invariant 3). When allow_mcp=true,
    MCP tools must be explicitly named in allowed_tools (Invariant 4).
    """
    # 1. Hard drop delegate_*, memory_*
    filtered = [t for t in all_tools if not _is_denied(t)]

    # 2. MCP handling
    if not cfg.allow_mcp:
        filtered = [t for t in filtered if not _is_mcp_tool(t)]
    else:
        # allow_mcp=true: MCP tools must be in allowed_tools explicitly
        filtered = [t for t in filtered if not _is_mcp_tool(t) or t["function"]["name"] in cfg.allowed_tools]

    # 3. Apply allowed_tools allowlist (intersection)
    if cfg.allowed_tools:
        filtered = [t for t in filtered if t["function"]["name"] in cfg.allowed_tools]

    return filtered


def _is_denied(tool: dict) -> bool:
    name = tool.get("function", {}).get("name", "")
    return any(name.startswith(prefix) for prefix in _HARD_DENY_PREFIXES)


def _is_mcp_tool(tool: dict) -> bool:
    """MCP tool detection. Prefer metadata, fallback to server__tool naming."""
    meta = tool.get("metadata") or tool.get("_meta") or {}
    if meta.get("origin") == "mcp":
        return True
    name = tool.get("function", {}).get("name", "")
    return "__" in name


def assert_invariants(cfg: SpecialistConfig, specialist_tools: list[dict]) -> None:
    """Runtime check (Decision 6/12/13). Raises AssertionError on violation."""
    for t in specialist_tools:
        name = t.get("function", {}).get("name", "")
        assert not name.startswith("delegate_"), f"Invariant 1: delegate_ tool leaked: {name}"
        assert not name.startswith("memory_"), f"Invariant 2: memory_ tool leaked: {name}"
        if not cfg.allow_mcp and _is_mcp_tool(t):
            raise AssertionError(f"Invariant 3: MCP tool {name} present with allow_mcp=false")


# --- Provider construction ---


def _make_specialist_provider(
    cfg: SpecialistConfig,
    specialist,
    app_config: dict,
) -> Any:
    """Create the provider for a specialist, with timeout capped to specialist budget.

    cfg.provider / cfg.model override specialist defaults; the full provider
    config dict is read from app_config['llm']['providers'].
    """
    from providers.factory import ProviderFactory
    provider_name = cfg.provider or specialist.default_provider
    model_name = cfg.model or specialist.default_model
    providers_cfg = app_config.get("llm", {}).get("providers", {})
    if provider_name not in providers_cfg:
        raise ValueError(
            f"Specialist {specialist.name!r}: provider {provider_name!r} not in config.yaml"
        )
    provider_config = dict(providers_cfg[provider_name])
    provider_config["model"] = model_name
    agent_cfg = dict(app_config.get("agent", {}))
    base_timeout = int(agent_cfg.get("timeout", cfg.timeout_seconds))
    agent_cfg["timeout"] = min(base_timeout, cfg.timeout_seconds)
    return ProviderFactory.create(provider_config, agent_cfg)


# --- Main run entry point ---


def run_specialist(
    registry: SpecialistRegistry,
    name: str,
    task: str,
    parent_session: Session,
    app_config: dict | None = None,
) -> ToolResult:
    """Execute a specialist. Returns ToolResult with content (prose) and data (structured).

    Never raises — all failures are converted to ToolResult(ok=False) per Decision 10.
    """
    start = time.monotonic()
    specialist = registry.get(name)
    cfg = registry.get_config(name)
    app_config = app_config or {}

    if specialist is None or cfg is None:
        return _preflight_error(name, "not_found")
    if not cfg.enabled:
        return _preflight_error(name, "disabled")

    try:
        # 1. Fresh session
        fresh = Session.new(parent_session.cwd, max_messages=parent_session.max_messages)
        fresh.workspace_root = parent_session.workspace_root

        # 2. Build effective tool set
        all_tools = get_tools_schema()
        specialist_tools = build_specialist_tools(cfg, all_tools)
        assert_invariants(cfg, specialist_tools)

        # 3. Inject specialist system prompt
        prompt = render_specialist_prompt(
            specialist.system_prompt_template,
            task=task,
            specialist_name=specialist.name,
            allowed_tools=cfg.allowed_tools,
        )
        fresh.add_message("system", prompt)

        # 4. Create sub-provider with capped timeout
        provider = _make_specialist_provider(cfg, specialist, app_config)

        # 5. Sub-AgentLoop
        sub_loop = AgentLoop(
            provider,
            fresh,
            tools_schema=specialist_tools,
            max_iterations=cfg.max_iterations,
        )

        # 6. Run with timeout
        display_events: list[dict] = []
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_run_sub_loop, sub_loop, task, display_events)
        try:
            result_text = future.result(timeout=cfg.timeout_seconds)
        except concurrent.futures.TimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            duration = int((time.monotonic() - start) * 1000)
            registry.record_invocation(name, ok=False, error_type="timeout",
                                        duration_ms=duration, content="", model=_effective_model(cfg, specialist))
            return _timeout_result(specialist, cfg, duration)
        finally:
            if future.done():
                executor.shutdown(wait=True)

        # 7. Triage contract validation
        if specialist.name == "triage":
            try:
                parsed = _parse_structured(result_text)
                rec = _normalize_recommended_specialist(parsed.get("recommended_specialist"))
                parsed["recommended_specialist"] = rec
                valid = set(registry.list_names()) | {"(none)"}
                if rec not in valid:
                    duration = int((time.monotonic() - start) * 1000)
                    registry.record_invocation(name, ok=False, error_type="contract_violation",
                                                duration_ms=duration, content=result_text,
                                                model=_effective_model(cfg, specialist))
                    return _contract_violation_result(specialist, parsed, registry)
            except ValueError:
                pass  # If we can't parse JSON, treat as freeform triage output

        # 8. Format result
        content = specialist.data_to_content(_try_parse(result_text), CONTENT_CAP_SPECIALIST)
        content = _cap_content(content, CONTENT_CAP_SPECIALIST)

        duration = int((time.monotonic() - start) * 1000)
        registry.record_invocation(name, ok=True, error_type=None,
                                    duration_ms=duration, content=content,
                                    model=_effective_model(cfg, specialist))

        return ToolResult(
            ok=True,
            content=content,
            data={
                "specialist": specialist.name,
                "model": _effective_model(cfg, specialist),
                "iterations": cfg.max_iterations,
                "duration_ms": duration,
                "result": _try_parse(result_text),
                "display_events": display_events,
            },
        )

    except Exception as e:
        duration = int((time.monotonic() - start) * 1000)
        logger.exception("Specialist %s crashed", name)
        registry.record_invocation(name, ok=False, error_type="crash",
                                    duration_ms=duration, content=str(e),
                                    model=_effective_model(cfg, specialist))
        return _crash_result(specialist, cfg, e, duration)


# --- Helpers ---


def _cap_content(content: str, cap: int) -> str:
    if len(content) <= cap:
        return content
    return content[: cap - len(_TRUNCATION_NOTICE)] + _TRUNCATION_NOTICE


def _run_sub_loop(sub_loop: AgentLoop, task: str, display_events: list[dict]) -> str:
    """Run a sub-AgentLoop and collect display-only tool events."""
    final_response = ""
    for event in sub_loop.run_stream(task):
        event_type = event.get("type")
        if event_type == "assistant_done":
            final_response = event.get("content", "")
        elif event_type in {"tool_start", "tool_end"}:
            display_events.append(_compact_display_event(event))
    return final_response


def _compact_display_event(event: dict) -> dict:
    event_type = event.get("type")
    compact = {
        "type": event_type,
        "tool_name": event.get("tool_name", "?"),
    }
    if event_type == "tool_start":
        compact["args"] = event.get("args", {})
    if event_type == "tool_end":
        compact["ok"] = bool(event.get("ok", False))
        compact["content"] = str(event.get("content", ""))[:200]
    return compact


def _effective_model(cfg: SpecialistConfig, specialist) -> str:
    return cfg.model or specialist.default_model


def _normalize_recommended_specialist(value: Any) -> str:
    if value is None:
        return "(none)"
    text = str(value).strip()
    if text.lower() in {"", "none", "(none)", "null"}:
        return "(none)"
    return text


def _try_parse(text: str) -> dict | str:
    """Try to parse text as JSON; return dict on success, original text on failure."""
    import json
    text = text.strip()
    if not text:
        return {}
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # Try to find JSON in code block
    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    return text


def _parse_structured(text: str) -> dict:
    """Strict parse: only accept JSON or fenced JSON block."""
    result = _try_parse(text)
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object, got: {type(result).__name__}")
    return result


def _preflight_error(name: str, kind: str) -> ToolResult:
    msg = {
        "not_found": f"Specialist {name!r} not found. Available: (check /specialists)",
        "disabled": f"Specialist {name!r} is disabled in config.yaml",
    }[kind]
    return ToolResult(ok=False, content=msg, data={"error_type": kind, "specialist": name})


def _timeout_result(specialist, cfg: SpecialistConfig, duration_ms: int) -> ToolResult:
    return ToolResult(
        ok=False,
        content=(
            f"Specialist {specialist.name} ({cfg.model or 'default model'}, "
            f"timeout {cfg.timeout_seconds}s) timed out after {duration_ms}ms.\n"
            f"The parent agent may retry with a smaller task, choose another specialist, or answer directly."
        ),
        data={
            "error_type": "timeout",
            "specialist": specialist.name,
            "model": cfg.model,
            "iterations": cfg.max_iterations,
            "elapsed_ms": duration_ms,
        },
    )


def _crash_result(specialist, cfg: SpecialistConfig, exc: Exception, duration_ms: int) -> ToolResult:
    detail = f"{type(exc).__name__}: {exc}"
    detail = detail[:200]  # truncate for data
    content = (
        f"✗ {specialist.name} ({cfg.model or 'default model'}, "
        f"iter {cfg.max_iterations}): crashed: {type(exc).__name__}"
    )[:CONTENT_CAP_ERROR]
    return ToolResult(
        ok=False,
        content=content,
        data={
            "error_type": "crash",
            "specialist": specialist.name,
            "model": cfg.model,
            "iterations": cfg.max_iterations,
            "elapsed_ms": duration_ms,
            "detail": detail,
        },
    )


def _contract_violation_result(specialist, parsed: dict, registry: SpecialistRegistry) -> ToolResult:
    rec = parsed.get("recommended_specialist", "(missing)")
    valid = ", ".join(registry.list_names()) or "(none)"
    return ToolResult(
        ok=False,
        content=(
            f"triage returned invalid recommended_specialist: {rec!r}. "
            f"Valid options: {valid}. Result not used for routing."
        ),
        data={
            "error_type": "contract_violation",
            "specialist": specialist.name,
            "detail": f"recommended_specialist={rec!r} not in registry",
            "result": parsed,
        },
    )
