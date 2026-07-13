"""Shared FastAPI backend dependencies.

This module keeps HTTP concerns separate from the existing service layer.
Routers import these helpers instead of loading config or constructing sessions
themselves.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import Request
from dotenv import load_dotenv

from providers.factory import ProviderFactory
from service.runtime_service import RuntimeContext, RuntimeService
from service.library_service import LibraryService


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    load_dotenv(os.path.join(get_workspace(), ".env"), override=False)
    config_path = os.getenv("BOBODAN_CONFIG", "config.yaml")
    return ProviderFactory.load_config(config_path)


def get_workspace() -> str:
    return os.path.abspath(os.getenv("BOBODAN_WORKSPACE", os.getcwd()))


def get_session_save_dir(
    config: dict[str, Any] | None = None,
    workspace: str | None = None,
) -> str:
    cfg = config or get_config()
    save_dir = cfg.get("session", {}).get("save_dir", ".session")
    if os.path.isabs(save_dir):
        return save_dir
    return os.path.join(workspace or get_workspace(), save_dir)


def get_default_provider_name(config: dict[str, Any] | None = None) -> str:
    cfg = config or get_config()
    return cfg.get("llm", {}).get("default_provider", "")


@lru_cache(maxsize=1)
def get_runtime_context() -> RuntimeContext:
    return RuntimeService.build_context(get_config(), get_workspace())


@lru_cache(maxsize=32)
def get_library_runtime_context(workspace: str) -> RuntimeContext:
    """Build a library-scoped runtime while keeping user memory and skills global."""
    context = RuntimeService.build_context(get_config(), workspace)
    global_context = get_runtime_context()
    context.skills_dir = global_context.skills_dir
    context.skills_prompt = global_context.skills_prompt
    context.skill_count = global_context.skill_count
    context.memory_manager = global_context.memory_manager
    context.memory_prompt = global_context.memory_prompt
    context.memory_count = global_context.memory_count
    return context


def get_library_service() -> LibraryService:
    return LibraryService()


def get_request_workspace(request: Request) -> str:
    return getattr(request.state, "library_workspace", get_workspace())


def get_request_library_id(request: Request) -> str | None:
    return getattr(request.state, "library_id", None)


def reset_dependency_caches() -> None:
    """Clear cached dependency state.

    Tests use this after overriding environment variables.
    """
    get_config.cache_clear()
    get_runtime_context.cache_clear()
    get_library_runtime_context.cache_clear()
