"""W1 E11 / D4：探索预算可由配置覆盖（默认为 AgentLoop 的推导值，不硬塞数字）。"""

from __future__ import annotations

from core.agent_loop import AgentLoop, SETTLEMENT_ROUNDS
from core.exploration_budget import resolve_exploration_budget


def test_no_config_means_the_loop_default():
    assert resolve_exploration_budget(None) is None
    assert resolve_exploration_budget({}) is None
    assert resolve_exploration_budget({"agent": {}}) is None


def test_an_explicit_budget_is_read():
    assert resolve_exploration_budget({"agent": {"exploration_budget": 4}}) == 4
    assert resolve_exploration_budget({"agent": {"exploration_budget": "3"}}) == 3


def test_a_nonsense_budget_falls_back_to_the_default():
    """配错了不猜：让默认值生效，而不是当成 0 轮探索。"""
    for raw in (0, -2, "abc", None, [], {}):
        assert resolve_exploration_budget({"agent": {"exploration_budget": raw}}) is None, raw
    assert resolve_exploration_budget({"agent": "not-a-dict"}) is None


def test_the_configured_budget_reaches_the_loop():
    from providers.types import LLMResponse

    class _Plain:
        name = "plain"
        model = "m"

        def complete(self, messages, tools=None, **kwargs):
            return LLMResponse(content="好")

        def get_name(self):
            return "plain"

    from core.session import Session

    budget = resolve_exploration_budget({"agent": {"exploration_budget": 2}})
    agent = AgentLoop(_Plain(), Session.new("/test"), max_iterations=8, exploration_budget=budget)

    assert agent.exploration_budget == 2
    # 没配置时回到推导默认（max_iterations − 结算期）。
    default_agent = AgentLoop(_Plain(), Session.new("/test"), max_iterations=8)
    assert default_agent.exploration_budget == 8 - SETTLEMENT_ROUNDS
