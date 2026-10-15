"""探索预算的配置读取（W1 E11 / D4）。

预算决定"多少轮之后进入结算期（不再开新检索）"。默认值由 «AgentLoop» 给
（«max_iterations - SETTLEMENT_ROUNDS»）；这里只负责把**显式配置**读出来，
读不出来就返回 None，让默认值生效 —— 不猜、不硬塞一个数字。
"""

from __future__ import annotations

#: 配置位置：«{"agent": {"exploration_budget": 4}}»
CONFIG_SECTION = "agent"
CONFIG_KEY = "exploration_budget"


def resolve_exploration_budget(config: dict | None) -> int | None:
    """显式配置的探索预算；没配或配得不合理时返回 None（沿用默认）。"""
    section = (config or {}).get(CONFIG_SECTION) or {}
    if not isinstance(section, dict):
        return None
    raw = section.get(CONFIG_KEY)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
