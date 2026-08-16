"""Unit tests for core.prompt_layout (AG-3.2)."""

from core.prompt_layout import (
    CACHE_BOUNDARY_MARKER,
    join_with_boundary,
    split_static_dynamic,
)


def test_join_with_boundary_inserts_marker():
    out = join_with_boundary("static prefix", "dynamic tail")
    assert CACHE_BOUNDARY_MARKER in out
    assert out.index("static prefix") < out.index(CACHE_BOUNDARY_MARKER) < out.index("dynamic tail")


def test_join_with_boundary_no_dynamic():
    assert join_with_boundary("static only", None) == "static only"
    assert join_with_boundary("static only", "   ") == "static only"


def test_join_with_boundary_no_static():
    assert join_with_boundary("", "dynamic") == "dynamic"


def test_split_static_dynamic_orders_parts():
    static, dynamic = split_static_dynamic([
        "<!-- bobodan:base-prompt --> identity",
        "<!-- bobodan:user-preferences --> prefs",
        "<!-- bobodan:request-scope --> scope",
    ])
    assert static == ["<!-- bobodan:base-prompt --> identity"]
    assert "<!-- bobodan:user-preferences --> prefs" in dynamic
    assert "<!-- bobodan:request-scope --> scope" in dynamic


def test_split_static_dynamic_all_static_when_no_marker():
    static, dynamic = split_static_dynamic(["identity", "rules"])
    assert static == ["identity", "rules"]
    assert dynamic == []
