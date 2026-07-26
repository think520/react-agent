"""L1 + L2 unit tests for cli/tool_display.

L1: parametrised tests for summarize_tool_args covering the explicit
table (Q5 A3), special cases, short-JSON fallback, no-args, and MCP.
L2: 7 coalesce state-machine cases from docs/NEXT_STEPS_EXECUTION_PLAN.md
plus "flush without pending emits empty".

The tests touch no I/O, no LLM, and no REPL state. They are pure.
"""

from __future__ import annotations

import pytest

from cli.tool_display import (
    CoalescerStack,
    SPINNER_FRAME_S,
    THINK_VERB_COLORS,
    THINK_VERB_DWELL_S,
    THINK_VERBS,
    ToolRunCoalescer,
    spinner_frame_at,
    status_style_for_verb,
    summarize_tool_args,
    think_verb_color_at,
    think_verb_at,
)


# --- L1: summarize_tool_args (Q5 A3) -----------------------------------------


def _path_tail(p: str, n: int) -> str:
    """Mirror of cli.tool_display._tail for use in test expected values."""
    return p[-n:] if len(p) > n else p


@pytest.mark.parametrize(
    "tool_name,args,limit,expected",
    [
        # Path-tail tools: read_file / write_file / list_dir / stat_path
        # When the path is longer than the limit, only the tail is shown.
        ("read_file", {"path": "/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p.md"}, 20,
         _path_tail("/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p.md", 20)),
        ("read_file", {"path": "/short.md"}, 60, "/short.md"),
        ("read_file", {"path": "/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p.md"}, 10,
         _path_tail("/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p.md", 10)),
        ("write_file", {"path": "/x/y/z/folder/that/is/far/away/file.md"}, 12,
         _path_tail("/x/y/z/folder/that/is/far/away/file.md", 12)),
        ("list_dir", {"path": "/short/dir/"}, 60, "/short/dir/"),
        ("stat_path", {"file_path": "/x/y/z/folder/that/is/far/away/d.md"}, 10,
         _path_tail("/x/y/z/folder/that/is/far/away/d.md", 10)),
        # No-args tools and missing keys
        ("read_file", None, 60, ""),
        ("read_file", {}, 60, ""),
        ("read_file", {"other": "x"}, 60, ""),
        # rag_search / concept_map_query
        ("rag_search", {"query": "transformer attention"}, 60, "transformer attention"),
        ("rag_search", {"query": "x" * 200}, 60, "x" * 59 + "…"),
        ("concept_map_query", {"concept": "neural nets"}, 60, "neural nets"),
        # delegate_triage / delegate_planner
        ("delegate_triage", {"query": "foo bar"}, 60, "foo bar"),
        ("delegate_planner", {"goal": "learn rust"}, 60, "learn rust"),
        # delegate_doc_reader
        ("delegate_doc_reader", {"source_paths": ["/x.md"]}, 60, "/x.md"),
        ("delegate_doc_reader", {"goal": "summarize it"}, 60, "summarize it"),
        ("delegate_doc_reader", {}, 60, ""),
        # change_dir / http_request
        ("change_dir", {"path": "/a/b/c/d/"}, 60, "/a/b/c/d/"),
        ("change_dir", {"path": "/x/y/z/folder/that/is/far/away/deep"}, 20,
         _path_tail("/x/y/z/folder/that/is/far/away/deep", 20)),
        ("http_request", {"method": "GET", "url": "https://x.com/foo"}, 60, "GET https://x.com/foo"),
        ("http_request", {"method": "post", "url": "https://x.com/foo"}, 60, "POST https://x.com/foo"),
        ("http_request", {"url": "https://x.com/foo"}, 60, "https://x.com/foo"),
        # MCP tools: short JSON fallback
        ("mcp__github__create_issue", {"title": "bug"}, 60, '{"title":"bug"}'),
        (
            "mcp__github__create_issue",
            {"title": "x" * 100, "body": "y" * 100},
            20,
            '{"title":"xxxxxxxxx…',
        ),
        # Other built-in tools: short JSON fallback
        ("memory_save", {"name": "foo"}, 60, '{"name":"foo"}'),
        ("knowledge_status", {}, 60, ""),
        ("memory_daily_read", {}, 60, ""),
    ],
)
def test_summarize_tool_args(tool_name, args, limit, expected):
    assert summarize_tool_args(tool_name, args, limit) == expected


def test_summarize_tool_args_short_json_falls_back_on_unserialisable():
    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    # json.dumps will fail; we should fall back to str(args) and truncate.
    out = summarize_tool_args("weird_tool", {"x": Opaque()}, 20)
    assert isinstance(out, str)
    assert len(out) <= 20


# --- L1: spinner/verb selection --------------------------------------------


def test_spinner_frame_at_advances_every_frame():
    assert spinner_frame_at(0.0) == "⠋"
    assert spinner_frame_at(SPINNER_FRAME_S) == "⠙"
    # index 4 = "⠼", index 5 = "⠴"
    assert spinner_frame_at(SPINNER_FRAME_S * 4) == "⠼"
    # wraps
    assert spinner_frame_at(SPINNER_FRAME_S * 10) == "⠋"


def test_think_verb_at_advances_every_dwell():
    assert think_verb_at(0.0) == THINK_VERBS[0]
    assert think_verb_at(THINK_VERB_DWELL_S) == THINK_VERBS[1]
    assert think_verb_at(THINK_VERB_DWELL_S * 4) == THINK_VERBS[4]
    # wraps
    assert think_verb_at(THINK_VERB_DWELL_S * 5) == THINK_VERBS[0]


def test_think_verb_colors_are_stable_and_distinct():
    assert set(THINK_VERB_COLORS) == set(THINK_VERBS)
    assert len(set(THINK_VERB_COLORS.values())) == len(THINK_VERBS)
    for verb in THINK_VERBS:
        assert status_style_for_verb(verb) == THINK_VERB_COLORS[verb]


def test_think_verb_color_at_follows_current_verb():
    assert think_verb_color_at(0.0) == THINK_VERB_COLORS[THINK_VERBS[0]]
    assert think_verb_color_at(THINK_VERB_DWELL_S) == THINK_VERB_COLORS[THINK_VERBS[1]]
    assert think_verb_color_at(THINK_VERB_DWELL_S * 4) == THINK_VERB_COLORS[THINK_VERBS[4]]


# --- L2: ToolRunCoalescer --------------------------------------------------


def test_coalescer_one_success_emits_no_summary():
    c = ToolRunCoalescer()
    assert c.record_start("read_file", 0.0) is None
    show, n = c.record_success(0.5)
    assert (show, n) == (True, 1)
    assert c.flush_payload() is None


def test_coalescer_two_successes_emit_no_summary():
    c = ToolRunCoalescer()
    c.record_start("read_file", 0.0)
    c.record_success(0.5)
    c.record_start("read_file", 1.0)
    show, n = c.record_success(1.5)
    assert (show, n) == (True, 2)
    assert c.flush_payload() is None


def test_coalescer_three_successes_emit_x3_marker_no_summary():
    """The ×3 marker is the inline caller signal at count == 3; flush is silent."""
    c = ToolRunCoalescer()
    c.record_start("read_file", 0.0)
    c.record_success(0.5)
    c.record_start("read_file", 1.0)
    c.record_success(1.5)
    c.record_start("read_file", 2.0)
    show, n = c.record_success(2.5)
    assert (show, n) == (True, 3)
    # count == 3, flush threshold is >3
    assert c.flush_payload() is None


def test_coalescer_eight_successes_emit_summary():
    c = ToolRunCoalescer()
    for i in range(8):
        c.record_start("read_file", float(i))
        c.record_success(float(i) + 0.5)
    payload = c.flush_payload()
    assert payload == "✓ read_file ×8 total 7.5s"


def test_coalescer_name_change_flushes_then_starts_new_run():
    c = ToolRunCoalescer()
    for i in range(4):
        c.record_start("read_file", float(i))
        c.record_success(float(i) + 0.5)
    payload = c.record_start("rag_search", 10.0)
    assert payload == "✓ read_file ×4 total 3.5s"
    # New run for rag_search starts at count 1
    show, n = c.record_success(10.5)
    assert (show, n) == (True, 1)


def test_coalescer_error_resets_count_and_breaks_run():
    c = ToolRunCoalescer()
    for i in range(3):
        c.record_start("read_file", float(i))
        c.record_success(float(i) + 0.5)
    # count == 3, error returns no summary (flush threshold is >3)
    assert c.record_error() is None
    # Run is broken; next call (even same name) starts at count 1
    c.record_start("read_file", 10.0)
    show, n = c.record_success(10.5)
    assert (show, n) == (True, 1)


def test_coalescer_error_after_four_emits_summary_then_resets():
    c = ToolRunCoalescer()
    for i in range(4):
        c.record_start("read_file", float(i))
        c.record_success(float(i) + 0.5)
    payload = c.record_error()
    assert payload == "✓ read_file ×4 total 3.5s"
    # Run is reset
    c.record_start("read_file", 10.0)
    show, n = c.record_success(10.5)
    assert (show, n) == (True, 1)


def test_coalescer_flush_without_pending_emits_empty():
    """Per Q8: a flush when there is no pending run returns None."""
    assert ToolRunCoalescer().flush_payload() is None
    c = ToolRunCoalescer()
    c.tool_name = "read_file"  # simulate stale state
    assert c.flush_payload() is None


# --- L2: CoalescerStack ----------------------------------------------------


def test_stack_main_scope_only():
    s = CoalescerStack()
    assert s.depth == 1
    for i in range(8):
        s.record_start("read_file", float(i))
        s.record_success(float(i) + 0.5)
    assert s.flush_current() == "✓ read_file ×8 total 7.5s"


def test_stack_scope_isolation_main_and_specialist_independent():
    s = CoalescerStack()
    # main: 2 read_file
    s.record_start("read_file", 0.0)
    s.record_success(0.5)
    s.record_start("read_file", 1.0)
    s.record_success(1.5)
    # push specialist scope
    s.push_scope()
    # specialist: 5 read_file
    for i in range(5):
        s.record_start("read_file", 10.0 + i)
        s.record_success(10.0 + i + 0.5)
    payload = s.pop_scope()
    assert payload == "✓ read_file ×5 total 4.5s"
    assert s.depth == 1
    # main is independent: count is still 2
    assert s.flush_current() is None


def test_stack_specialist_error_does_not_affect_main():
    s = CoalescerStack()
    s.record_start("read_file", 0.0)
    s.record_success(0.5)
    s.record_start("read_file", 1.0)
    s.record_success(1.5)
    s.push_scope()
    for i in range(3):
        s.record_start("read_file", 10.0 + i)
        s.record_success(10.0 + i + 0.5)
    # count == 3, error returns no summary
    assert s.record_error() is None
    assert s.pop_scope() is None
    assert s.flush_current() is None


def test_stack_pop_main_scope_is_noop():
    s = CoalescerStack()
    # Cannot pop the main scope
    assert s.pop_scope() is None
    assert s.depth == 1
