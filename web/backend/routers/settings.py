"""Settings and runtime summary endpoints."""

from __future__ import annotations

import os

from fastapi import APIRouter

from core.skills import list_skills
from service.agent_service import AgentService
from web.backend.capabilities import WEB_SKILL_NAMES
from web.backend.deps import get_config, get_default_provider_name, get_workspace

router = APIRouter()


@router.get("")
def settings() -> dict:
    config = get_config()
    workspace = get_workspace()
    skills_config = config.get("skills", {})
    skills_dir = skills_config.get("dir", "skills")
    if not os.path.isabs(skills_dir):
        skills_dir = os.path.join(workspace, skills_dir)
    skills = [
        skill for skill in list_skills(skills_dir)
        if skill.name in WEB_SKILL_NAMES
    ] if skills_config.get("enabled", True) else []
    return {
        "ok": True,
        "workspace_name": os.path.basename(workspace),
        "default_provider": get_default_provider_name(config),
        "providers": AgentService.list_providers(config)["providers"],
        "mcp_enabled": bool(config.get("mcp", {}).get("enabled", False)),
        "skills": [
            {"name": skill.name, "description": skill.description}
            for skill in skills
        ],
    }
