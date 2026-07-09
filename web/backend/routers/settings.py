"""Settings and runtime summary endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from service.agent_service import AgentService
from web.backend.deps import get_config, get_default_provider_name, get_workspace

router = APIRouter()


@router.get("")
def settings() -> dict:
    config = get_config()
    return {
        "ok": True,
        "workspace": get_workspace(),
        "default_provider": get_default_provider_name(config),
        "providers": AgentService.list_providers(config)["providers"],
        "mcp_enabled": bool(config.get("mcp", {}).get("enabled", False)),
    }
