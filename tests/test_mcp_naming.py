"""Tests for mcp_client.naming."""

import pytest

from mcp_client.naming import (
    SERVER_NAME_MAX,
    TOOL_NAME_MAX,
    TOOL_NAME_SEPARATOR,
    build_safe_tool_name,
    sanitize_server_name,
    sanitize_tool_name,
)


# --- sanitize_server_name ---


def test_server_name_simple():
    assert sanitize_server_name("github") == "github"


def test_server_name_with_dash_underscore():
    assert sanitize_server_name("my-cool_server") == "my-cool_server"


def test_server_name_replaces_special_chars():
    assert sanitize_server_name("context7/mcp!") == "context7-mcp-"


def test_server_name_unicode_to_dash():
    assert sanitize_server_name("服务器") == "---"  # 3 CJK chars → 3 dashes


def test_server_name_truncates_to_max():
    long = "a" * 50
    out = sanitize_server_name(long)
    assert len(out) == SERVER_NAME_MAX
    assert out == "a" * SERVER_NAME_MAX


def test_server_name_truncation_exact():
    assert len(sanitize_server_name("a" * 30)) == 30


# --- sanitize_tool_name ---


def test_tool_name_simple():
    assert sanitize_tool_name("create_issue") == "create_issue"


def test_tool_name_replaces_special():
    assert sanitize_tool_name("get-docs.v2") == "get-docs-v2"


def test_tool_name_no_truncate():
    long = "t" * 100
    assert sanitize_tool_name(long) == long


# --- build_safe_tool_name ---


def test_basic():
    assert build_safe_tool_name("github", "create_issue") == "github__create_issue"


def test_dash_in_tool():
    assert build_safe_tool_name("context7", "get-docs") == "context7__get-docs"


def test_separator_used():
    out = build_safe_tool_name("a", "b")
    assert TOOL_NAME_SEPARATOR in out
    assert out == "a__b"


def test_total_length_capped():
    """The combined name should never exceed TOOL_NAME_MAX."""
    server = "s" * 40  # would normally exceed 30, gets truncated
    tool = "t" * 40
    out = build_safe_tool_name(server, tool)
    assert len(out) <= TOOL_NAME_MAX


def test_long_server_name_truncated():
    out = build_safe_tool_name("a" * 50, "x")
    # server truncated to 30
    assert out.startswith("a" * 30)
    assert out.endswith("__x")


def test_long_tool_name_truncated():
    server = "github"
    tool = "t" * 80
    out = build_safe_tool_name(server, tool)
    # 6 (github) + 2 (__) + 56 (tool) = 64
    assert len(out) == TOOL_NAME_MAX


def test_reserved_collision_appends_suffix():
    reserved = {"github__create_issue"}
    out = build_safe_tool_name("github", "create_issue", reserved=reserved)
    assert out == "github__create_issue-2"
    assert out not in reserved


def test_reserved_collision_increments():
    reserved = {
        "github__create_issue",
        "github__create_issue-2",
        "github__create_issue-3",
    }
    out = build_safe_tool_name("github", "create_issue", reserved=reserved)
    assert out == "github__create_issue-4"


def test_reserved_collision_handles_truncation():
    """Even when the name is truncated, the suffix slot must be available."""
    reserved = set()
    # First call: no collision, get the longest possible name
    first = build_safe_tool_name("a" * 30, "t" * 32, reserved=reserved)
    reserved.add(first)
    # Second call: same inputs, must add suffix; truncate tool part to make room
    second = build_safe_tool_name("a" * 30, "t" * 32, reserved=reserved)
    assert second != first
    assert second.endswith("-2")
    assert len(second) <= TOOL_NAME_MAX


def test_empty_reserved():
    out = build_safe_tool_name("x", "y", reserved=set())
    assert out == "x__y"
