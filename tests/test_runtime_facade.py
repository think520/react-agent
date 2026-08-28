"""Contract tests for the AG-0.5 runtime facade."""

import core.runtime as rt
from core.stream_guard import GuardedProvider
from providers.factory import ProviderFactory
from tools import TOOL_REGISTRY, ToolResult, execute_tool, get_tools_schema
from tools.base import register_tool


def test_facade_re_exports_tool_surface():
    assert rt.get_tools_schema is get_tools_schema
    assert rt.execute_tool is execute_tool
    assert rt.ToolResult is ToolResult
    assert rt.register_tool is register_tool
    assert rt.TOOL_REGISTRY is TOOL_REGISTRY


def test_facade_re_exports_provider_surface():
    assert rt.ProviderFactory is ProviderFactory
    assert rt.GuardedProvider is GuardedProvider
    assert callable(rt.guard_provider)


def test_facade_re_exports_memory_store():
    from memory.personal_store import PersonalKnowledgeStore

    assert rt.PersonalKnowledgeStore is PersonalKnowledgeStore


def test_create_provider_returns_guarded_provider():
    provider = rt.create_provider(
        {"type": "deepseek", "api_key": "test-key", "model": "deepseek-chat"},
        {"temperature": 0.7, "timeout": 5, "max_retries": 1},
        model="deepseek-chat",
    )
    assert isinstance(provider, GuardedProvider)
    assert provider.name == "deepseek"


def test_guard_provider_wraps_existing_provider():
    class FakeProvider:
        name = "fake"
        model = "m"

        def complete(self, messages, tools=None):
            return None

    guarded = rt.guard_provider(FakeProvider())
    assert isinstance(guarded, GuardedProvider)
    assert guarded.name == "fake"
