"""Tests for shared CLI/Web runtime composition."""

from service.runtime_service import RuntimeService


def test_runtime_context_loads_workspace_skills_and_personal_knowledge(tmp_path):
    skill_dir = tmp_path / "skills" / "study"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: study\ndescription: Study helper\n---\nUse study tools.",
        encoding="utf-8",
    )
    config = {
        "skills": {"enabled": True, "dir": "skills"},
        "memory": {"enabled": True, "dir": ".bobodan"},
    }

    context = RuntimeService.build_context(config, str(tmp_path))

    assert context.workspace == str(tmp_path.resolve())
    assert context.skill_count == 1
    assert "Study helper" in context.skills_prompt
    assert context.memory_count == 0


def test_runtime_context_refreshes_memory_between_runs(tmp_path):
    from service.memory_service import MemoryService

    context = RuntimeService.build_context(
        {"memory": {"enabled": True, "dir": ".bobodan"}},
        str(tmp_path),
    )
    MemoryService(str(tmp_path)).create_knowledge(
        scope="library",
        kind="learning_strategy",
        title="讲解偏好",
        content="喜欢先看例子",
    )

    result = context.refresh_memory()

    assert result is None
    assert context.memory_count == 1


def test_runtime_create_provider_uses_requested_config(monkeypatch):
    captured = {}

    def fake_create(provider_config, agent_config):
        captured["provider"] = provider_config
        captured["agent"] = agent_config
        return object()

    monkeypatch.setattr("service.runtime_service.ProviderFactory.create", fake_create)
    config = {
        "llm": {
            "default_provider": "first",
            "providers": {
                "first": {"type": "deepseek", "model": "one"},
                "second": {"type": "deepseek", "model": "two"},
            },
        },
        "agent": {"timeout": 12},
    }

    RuntimeService.create_provider(config, "second")

    assert captured["provider"]["model"] == "two"
    assert captured["agent"] == {"timeout": 12}
