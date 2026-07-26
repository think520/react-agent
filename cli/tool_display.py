"""Pure display primitives for the B-lite tool call UI.

Extracted from cli/repl.py so the summarizer, coalescer, spinner and verb
selection can be unit-tested without a live REPL. The REPL is the only
caller; the module exposes no IO, no global state, and no Rich / prompt
toolkit dependencies. The Active-line state machine (cursor ownership,
seal conditions) lives in repl.py because it is fundamentally about
orchestrating the event loop, not about display.

Layout:
  - Constants: SPINNER_FRAMES, THINK_VERBS (Q6: Bobodan verb list)
  - Pure functions: spinner_frame_at, think_verb_at, summarize_tool_args
  - State machine: ToolRunCoalescer, CoalescerStack

Per docs/NEXT_STEPS_EXECUTION_PLAN.md P0:
  - High-frequency tools get explicit summaries (Q5 A3)
  - change_dir / http_request get special rules
  - Other built-in tools and MCP tools fall back to short JSON
  - Coalesce applies to consecutive successful calls of the same name only
  - Errors pass through and reset the run (Q3 C1 wall clock semantics)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# --- Animation primitives ---------------------------------------------------

SPINNER_FRAMES: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
SPINNER_FRAME_S: float = 0.1

# Q6: Bobodan-specific verbs, title case, abstract work-in-progress (not
# stage-specific). The thinking line does not know the real state; specific
# actions are expressed by the tool active line.
THINK_VERBS: tuple[str, ...] = (
    "Thinking",
    "Checking",
    "Working",
    "Drafting",
    "Polishing",
)
THINK_VERB_DWELL_S: float = 2.5

THINK_VERB_COLORS: dict[str, str] = {
    "Thinking": "\033[38;5;39m",   # ink blue / cyan
    "Checking": "\033[38;5;75m",   # soft blue
    "Working": "\033[38;5;209m",   # clay / orange
    "Drafting": "\033[38;5;181m",  # muted petal
    "Polishing": "\033[38;5;108m", # sage green
}


def spinner_frame_at(elapsed_s: float) -> str:
    """Return the spinner frame shown at the given elapsed time."""
    idx = int(elapsed_s / SPINNER_FRAME_S) % len(SPINNER_FRAMES)
    return SPINNER_FRAMES[idx]


def think_verb_at(elapsed_s: float) -> str:
    """Return the thinking verb shown at the given elapsed time."""
    idx = int(elapsed_s / THINK_VERB_DWELL_S) % len(THINK_VERBS)
    return THINK_VERBS[idx]


def status_style_for_verb(verb: str) -> str:
    """Return the ANSI color used for a status verb."""
    return THINK_VERB_COLORS.get(verb, THINK_VERB_COLORS["Thinking"])


def think_verb_color_at(elapsed_s: float) -> str:
    """Return the ANSI color for the status verb at the given elapsed time."""
    return status_style_for_verb(think_verb_at(elapsed_s))


# --- Tool arg summarization (Q5 A3) -----------------------------------------

_PATH_TOOLS = frozenset({"read_file", "write_file", "list_dir", "stat_path"})
_QUERY_TOOLS = frozenset({"rag_search", "concept_map_query"})
_QUERY_KEY_BY_TOOL = {"rag_search": "query", "concept_map_query": "concept"}


def _tail(s: str, n: int) -> str:
    if not s:
        return ""
    return s[-n:] if len(s) > n else s


def _truncate(s: str, n: int) -> str:
    """Head-truncate to n characters; append ellipsis when shortened."""
    if not s or len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


def _short_json(args: dict, limit: int) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(args)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _delegate_doc_reader_summary(args: dict, limit: int) -> str:
    sources = args.get("source_paths") or []
    goal = args.get("goal") or ""
    path_part = _tail(str(sources[-1]), limit // 2) if isinstance(sources, list) and sources else ""
    remaining = max(0, limit - len(path_part) - 1)
    goal_part = _truncate(str(goal), remaining) if path_part else _truncate(str(goal), limit)
    if path_part and goal_part:
        return f"{path_part} {goal_part}"
    return path_part or goal_part


def summarize_tool_args(
    tool_name: str,
    args: dict | None,
    limit: int = 60,
) -> str:
    """Return a short human-readable summary of a tool's args, or ""."""
    if not args:
        return ""
    if tool_name.startswith("mcp__"):
        return _short_json(args, limit)
    if tool_name in _PATH_TOOLS:
        path = args.get("path") or args.get("file_path") or args.get("target") or ""
        return _tail(str(path), limit)
    if tool_name in _QUERY_TOOLS:
        key = _QUERY_KEY_BY_TOOL.get(tool_name, "query")
        return _truncate(str(args.get(key, "")), limit)
    if tool_name == "delegate_doc_reader":
        return _delegate_doc_reader_summary(args, limit)
    if tool_name == "delegate_triage":
        return _truncate(str(args.get("query", "")), limit)
    if tool_name == "delegate_planner":
        return _truncate(str(args.get("goal", "")), limit)
    if tool_name == "change_dir":
        return _tail(str(args.get("path", "")), limit)
    if tool_name == "http_request":
        method = str(args.get("method", "")).upper()
        url_budget = max(0, limit - len(method) - 1)
        url = _truncate(str(args.get("url", "")), url_budget)
        return f"{method} {url}".strip()
    return _short_json(args, limit)


# --- Coalescer state machine (Q1, Q3 C1) -----------------------------------

# Inline display for runs of 1, 2, or 3. After 3, the inline marker "×3" is
# emitted once and further calls are silent until the run is flushed. A flush
# emits "✓ name ×N total Ts" only when N > 3.
_MAX_INLINE_COUNT = 3
_FLUSH_THRESHOLD = 3


@dataclass
class ToolRunCoalescer:
    """Coalesces consecutive successful calls of one tool name.

    One run = one tool_name. A run is broken (count reset) by:
      - a different tool_name being started (record_start)
      - an error tool_end (record_error)
      - an explicit flush (flush_payload)

    On every successful call the caller receives (should_show_inline, count)
    so it can render either "✓ name" (1 or 2), "✓ name ×3" (one-time
    inline marker) or nothing (4+). The wall-clock elapsed for the run is
    computed on flush as last_success_ts - first_start_ts.
    """

    tool_name: str = ""
    _count: int = 0
    _run_start_ts: float = 0.0
    _last_success_ts: float = 0.0

    def record_start(self, tool_name: str, ts: float) -> str | None:
        """Record a tool_start. Flushes the prior run if name changes."""
        if self.tool_name and self.tool_name != tool_name:
            payload = self.flush_payload()
            self.tool_name = tool_name
            self._run_start_ts = ts
            return payload
        if not self.tool_name:
            self.tool_name = tool_name
        if self._count == 0:
            self._run_start_ts = ts
        return None

    def record_success(self, ts: float) -> tuple[bool, int]:
        """Register a successful call. Returns (show_inline, count)."""
        self._count += 1
        self._last_success_ts = ts
        if self._count <= _MAX_INLINE_COUNT:
            return True, self._count
        return False, self._count

    def record_error(self) -> str | None:
        """Register an error. Flushes the run, resets, returns flush payload."""
        payload = self.flush_payload()
        return payload

    def flush_payload(self) -> str | None:
        """Return the summary line if count > flush threshold, else None."""
        if self._count <= _FLUSH_THRESHOLD or not self.tool_name:
            self._count = 0
            self._run_start_ts = 0.0
            self._last_success_ts = 0.0
            return None
        elapsed = self._last_success_ts - self._run_start_ts
        payload = f"✓ {self.tool_name} ×{self._count} total {elapsed:.1f}s"
        self._count = 0
        self._run_start_ts = 0.0
        self._last_success_ts = 0.0
        return payload


class CoalescerStack:
    """Stack of Coalescers, one per visual scope.

    Bottom of the stack is always the main agent scope. When a delegate_*
    tool starts, a new empty scope is pushed. When the delegate_* tool
    ends, the scope is popped and any pending summary is returned to the
    caller for rendering. The current (top) scope is where new tool
    events are recorded.
    """

    def __init__(self) -> None:
        self._stack: list[ToolRunCoalescer] = [ToolRunCoalescer()]

    def record_start(self, tool_name: str, ts: float) -> str | None:
        return self._stack[-1].record_start(tool_name, ts)

    def record_success(self, ts: float) -> tuple[bool, int]:
        return self._stack[-1].record_success(ts)

    def record_error(self) -> str | None:
        return self._stack[-1].record_error()

    def push_scope(self) -> None:
        """Enter a new visual scope (specialist). The new scope is empty."""
        self._stack.append(ToolRunCoalescer())

    def pop_scope(self) -> str | None:
        """Leave the current visual scope. Returns any flush payload."""
        if len(self._stack) <= 1:
            return None
        payload = self._stack[-1].flush_payload()
        self._stack.pop()
        return payload

    def flush_current(self) -> str | None:
        """Flush the current scope (e.g., at turn end)."""
        return self._stack[-1].flush_payload()

    @property
    def depth(self) -> int:
        return len(self._stack)
