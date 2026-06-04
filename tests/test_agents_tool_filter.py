"""Tests for build_specialist_tools — covers all 4 hard invariants."""
from __future__ import annotations

from agents.config import SpecialistConfig
from agents.runner import build_specialist_tools, assert_invariants


def _tool(name: str, origin: str | None = None) -> dict:
    t = {"function": {"name": name, "description": name}}
    if origin:
        t["metadata"] = {"origin": origin}
    return t


def test_delegate_tools_always_denied():
    """Invariant 1: delegate_* tools never appear in specialist toolset."""
    cfg = SpecialistConfig(
        name="x",
        allowed_tools=["read_file", "delegate_doc_reader", "delegate_triage", "delegate_planner"],
    )
    tools = [_tool("read_file"), _tool("delegate_doc_reader"),
             _tool("delegate_triage"), _tool("delegate_planner")]
    result = build_specialist_tools(cfg, tools)
    names = {t["function"]["name"] for t in result}
    assert "read_file" in names
    assert "delegate_doc_reader" not in names
    assert "delegate_triage" not in names
    assert "delegate_planner" not in names


def test_memory_tools_always_denied():
    """Invariant 2: memory_* tools never appear in specialist toolset."""
    cfg = SpecialistConfig(
        name="x",
        allowed_tools=["read_file", "memory_recall", "memory_save", "memory_search"],
    )
    tools = [_tool("read_file"), _tool("memory_recall"), _tool("memory_save"),
             _tool("memory_search")]
    result = build_specialist_tools(cfg, tools)
    names = {t["function"]["name"] for t in result}
    assert "read_file" in names
    for n in ("memory_recall", "memory_save", "memory_search"):
        assert n not in names


def test_mcp_default_denied():
    """Invariant 3: allow_mcp=false (default) excludes MCP tools (server__tool pattern)."""
    cfg = SpecialistConfig(name="x", allowed_tools=["all", "*", "amap-maps__maps_geo"])
    tools = [_tool("read_file"), _tool("amap-maps__maps_geo"),
             _tool("github__search_issues")]
    result = build_specialist_tools(cfg, tools)
    names = {t["function"]["name"] for t in result}
    assert "read_file" not in names  # not in allowed_tools
    assert "amap-maps__maps_geo" not in names
    assert "github__search_issues" not in names


def test_mcp_metadata_also_denied():
    """MCP tools with metadata origin=mcp are also denied by default."""
    cfg = SpecialistConfig(name="x", allowed_tools=["amap-maps__maps_geo"])
    tools = [_tool("read_file"), _tool("amap-maps__maps_geo", origin="mcp")]
    result = build_specialist_tools(cfg, tools)
    names = {t["function"]["name"] for t in result}
    assert "amap-maps__maps_geo" not in names


def test_mcp_optin_requires_exact_allowlist():
    """Invariant 4: allow_mcp=true only includes MCP tools explicitly named in allowed_tools."""
    cfg = SpecialistConfig(
        name="x", allow_mcp=True,
        allowed_tools=["amap-maps__maps_geo", "read_file"],
    )
    tools = [_tool("read_file"), _tool("amap-maps__maps_geo"),
             _tool("github__search_issues")]
    result = build_specialist_tools(cfg, tools)
    names = {t["function"]["name"] for t in result}
    assert "read_file" in names
    assert "amap-maps__maps_geo" in names
    assert "github__search_issues" not in names  # not explicitly named


def test_mcp_optin_wildcard_does_not_include_mcp():
    """allow_mcp=true with ['*'] or ['all'] does NOT include MCP tools (Decision 13 two-door)."""
    cfg = SpecialistConfig(name="x", allow_mcp=True, allowed_tools=["*"])
    tools = [_tool("read_file"), _tool("amap-maps__maps_geo"),
             _tool("github__search_issues")]
    result = build_specialist_tools(cfg, tools)
    names = {t["function"]["name"] for t in result}
    assert "amap-maps__maps_geo" not in names
    assert "github__search_issues" not in names


def test_invariant_assertion_passes():
    """assert_invariants should not raise on a clean toolset."""
    cfg = SpecialistConfig(name="x", allowed_tools=["read_file"])
    tools = [_tool("read_file")]
    result = build_specialist_tools(cfg, tools)
    assert_invariants(cfg, result)  # no exception


def test_invariant_assertion_catches_leak():
    """assert_invariants should raise if a delegate_ tool sneaks in."""
    cfg = SpecialistConfig(name="x")
    bad_tools = [_tool("read_file"), _tool("delegate_doc_reader")]
    # Manually construct (filter would normally remove; this tests the assertion layer)
    try:
        assert_invariants(cfg, bad_tools)
    except AssertionError as e:
        assert "delegate_" in str(e)
    else:
        pytest.fail("AssertionError not raised")
