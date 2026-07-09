"""Shared FastAPI backend dependencies.

This module keeps HTTP concerns separate from the existing service layer.
Routers import these helpers instead of loading config or constructing sessions
themselves.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from providers.factory import ProviderFactory


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    config_path = os.getenv("BOBODAN_CONFIG", "config.yaml")
    return ProviderFactory.load_config(config_path)


def get_workspace() -> str:
    return os.path.abspath(os.getenv("BOBODAN_WORKSPACE", os.getcwd()))


def get_session_save_dir(config: dict[str, Any] | None = None) -> str:
    cfg = config or get_config()
    save_dir = cfg.get("session", {}).get("save_dir", ".session")
    if os.path.isabs(save_dir):
        return save_dir
    return os.path.join(get_workspace(), save_dir)


def get_default_provider_name(config: dict[str, Any] | None = None) -> str:
    cfg = config or get_config()
    return cfg.get("llm", {}).get("default_provider", "")


def reset_dependency_caches() -> None:
    """Clear cached dependency state.

    Tests use this after overriding environment variables.
    """
    get_config.cache_clear()
