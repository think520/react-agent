"""Provider facade (AG-0.5): the single door to provider creation.

Centralizes provider construction and stream guarding so a future swap to an
alternate provider system (or Pi SDK) only touches this module.
"""

from __future__ import annotations

from typing import Any

from core.stream_guard import GuardedProvider
from providers.factory import ProviderFactory


def create_provider(
    provider_config: dict,
    agent_config: dict,
    model: str | None = None,
) -> GuardedProvider:
    """Create a guarded provider from raw config blocks."""
    provider = ProviderFactory.create(provider_config, agent_config, model=model)
    return GuardedProvider(provider)


def guard_provider(provider: Any) -> GuardedProvider:
    """Wrap an existing provider with the stream guard (AG-0.4)."""
    return GuardedProvider(provider)


__all__ = ["create_provider", "guard_provider", "GuardedProvider", "ProviderFactory"]
