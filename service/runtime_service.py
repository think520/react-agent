"""Application runtime composition shared by CLI and Web entry points."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from core.skills import build_skills_system_prompt, list_skills
from core.trace import TraceWriter
from providers.factory import ProviderFactory


@dataclass
class RuntimeContext:
    workspace: str
    config: dict[str, Any]
    skills_dir: str
    skills_prompt: str | None
    skill_count: int
    memory_count: int

    def refresh_memory(self) -> None:
        """Refresh the structured personal-knowledge count for status UI."""
        from service.memory_service import MemoryService

        result = MemoryService(self.workspace).overview()
        self.memory_count = int(result.get("knowledge_count") or 0) if result.get("ok") else 0

    def create_provider(self, provider_name: str | None = None):
        return RuntimeService.create_provider(self.config, provider_name)

    def create_trace(self, session_id: str) -> TraceWriter:
        return TraceWriter(session_id, self.workspace)


class RuntimeService:
    @staticmethod
    def create_provider(config: dict[str, Any], provider_name: str | None = None):
        llm_config = config.get("llm", {})
        name = provider_name or llm_config.get("default_provider", "")
        providers = llm_config.get("providers") or {}
        provider_config = providers.get(name)
        if not provider_config:
            available = ", ".join(sorted(providers)) or "(none)"
            raise ValueError(f"Unknown provider '{name}'. Available: {available}")
        return ProviderFactory.create(provider_config, config.get("agent", {}))

    @staticmethod
    def build_context(config: dict[str, Any], workspace: str) -> RuntimeContext:
        workspace = os.path.abspath(workspace)

        skills_config = config.get("skills", {})
        skills_enabled = skills_config.get("enabled", True)
        skills_dir = skills_config.get("dir", "skills")
        if not os.path.isabs(skills_dir):
            skills_dir = os.path.join(workspace, skills_dir)
        skills_prompt = build_skills_system_prompt(skills_dir) if skills_enabled else None
        skill_count = len(list_skills(skills_dir)) if skills_enabled else 0

        memory_count = 0
        memory_config = config.get("memory", {})
        if memory_config.get("enabled", True):
            from service.memory_service import MemoryService

            result = MemoryService(workspace).overview()
            if result.get("ok"):
                memory_count = int(result.get("knowledge_count") or 0)

        return RuntimeContext(
            workspace=workspace,
            config=config,
            skills_dir=skills_dir,
            skills_prompt=skills_prompt,
            skill_count=skill_count,
            memory_count=memory_count,
        )

    @staticmethod
    def load_default_config() -> dict[str, Any]:
        return ProviderFactory.load_config(os.getenv("BOBODAN_CONFIG", "config.yaml"))
