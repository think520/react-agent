"""P5G.4: provider catalog — migration, key fallback, presets, CRUD, model fetch."""

import json
import os

import pytest

from providers import catalog
from providers.factory import ProviderFactory
from service.agent_service import AgentService


def _write_config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_migrates_legacy_config_once(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("BOBODAN_HOME", str(home))
    config_path = _write_config(
        tmp_path,
        """
llm:
  default_provider: deepseek
  providers:
    deepseek:
      type: deepseek
      api_key_env: TEST_KEY
      model: test-model
""",
    )
    os.environ["TEST_KEY"] = "test-key"

    config = ProviderFactory.load_config(config_path)
    assert config["llm"]["default_provider"] == "deepseek"
    assert "deepseek" in config["llm"]["providers"]

    # 文件已写盘，且后续加载不再重复迁移
    assert (home / "provider.json").is_file()
    mtime = (home / "provider.json").stat().st_mtime
    ProviderFactory.load_config(config_path)
    assert (home / "provider.json").stat().st_mtime == mtime


def test_key_falls_back_to_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FALLBACK_KEY", "env-value")
    assert catalog.resolve_api_key({"api_key": "", "api_key_env": "FALLBACK_KEY"}) == "env-value"
    assert catalog.resolve_api_key({"api_key": "direct", "api_key_env": "FALLBACK_KEY"}) == "direct"
    assert catalog.resolve_api_key({"api_key": "", "api_key_env": ""}) == ""


def test_presets_fill_fresh_install(tmp_path, monkeypatch):
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "home"))
    config = ProviderFactory.load_config(_write_config(tmp_path, "llm: {}\n"))
    providers = config["llm"]["providers"]
    assert "deepseek" in providers and "ollama" in providers
    # 全新安装不写文件（模板只在内存）
    assert not (tmp_path / "home" / "provider.json").exists()


def test_upsert_creates_file_and_delete_hides_preset(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("BOBODAN_HOME", str(home))
    ProviderFactory.load_config(_write_config(tmp_path, "llm: {}\n"))

    catalog.upsert_provider("ollama", {
        "type": "openai_compatible",
        "provider_name": "ollama",
        "base_url": "http://localhost:11434/v1",
        "api_key": "",
        "model_default": "qwen2.5",
        "models": [{"id": "qwen2.5", "name": "Qwen 2.5"}],
    })
    assert (home / "provider.json").is_file()

    # 文件存在后以文件为准：删除模板不复活
    assert catalog.delete_provider("ollama") is True
    assert catalog.delete_provider("unknown") is False
    config = ProviderFactory.load_config(_write_config(tmp_path, "llm: {}\n"))
    assert "ollama" not in config["llm"]["providers"]


def test_upsert_keeps_existing_key_when_blank(tmp_path, monkeypatch):
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "home"))
    ProviderFactory.load_config(_write_config(tmp_path, "llm: {}\n"))
    catalog.upsert_provider("deepseek", {
        "type": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-secret",
        "models": [{"id": "deepseek-chat", "name": "DeepSeek Chat"}],
        "model_default": "deepseek-chat",
    })
    # 编辑时 api_key 为空 → 保留原 key
    catalog.upsert_provider("deepseek", {
        "type": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "models": [{"id": "deepseek-chat", "name": "DeepSeek Chat"}],
        "model_default": "deepseek-chat",
    })
    saved = json.loads((tmp_path / "home" / "provider.json").read_text(encoding="utf-8"))
    assert saved["providers"]["deepseek"]["api_key"] == "sk-secret"


def test_list_providers_exposes_models_and_default(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("BOBODAN_HOME", str(home))
    catalog.upsert_provider("mine", {
        "type": "openai_compatible",
        "provider_name": "mine",
        "base_url": "https://example.com/v1",
        "api_key": "sk-abc",
        "model_default": "m1",
        "models": [{"id": "m1", "name": "M1"}, {"id": "m2", "name": "M2"}],
    })
    config = ProviderFactory.load_config(_write_config(tmp_path, "llm:\n  default_provider: mine\n"))
    result = AgentService.list_providers(config)
    entry = next(item for item in result["providers"] if item["name"] == "mine")
    assert entry["model"] == "m1"
    assert entry["models"] == [{"id": "m1", "name": "M1"}, {"id": "m2", "name": "M2"}]
    assert entry["configured"] is True
    assert entry["is_default"] is True


def test_factory_create_overrides_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = ProviderFactory.create(
        {"type": "openai", "api_key_env": "OPENAI_API_KEY", "model": "gpt-4", "base_url": "https://api.openai.com/v1"},
        {},
        model="gpt-4o",
    )
    assert provider.model == "gpt-4o"


def test_fetch_models_parses_openai_payload(monkeypatch, tmp_path):
    import httpx

    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "home"))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"object": "list", "data": [{"id": "b-model"}, {"id": "a-model"}]}

    monkeypatch.setattr(httpx, "get", lambda url, headers=None, timeout=10: FakeResponse())
    from web.backend.routers import settings

    result = settings.fetch_provider_models.__wrapped__ if hasattr(settings.fetch_provider_models, "__wrapped__") else settings.fetch_provider_models
    # 直接调用路由函数（绕过 FastAPI 层）
    from web.backend.routers.settings import ProviderFetchModelsRequest

    response = settings.fetch_provider_models(ProviderFetchModelsRequest(base_url="https://example.com/v1", api_key="k"))
    assert response["ok"] is True
    assert [m["id"] for m in response["models"]] == ["a-model", "b-model"]


def test_fetch_models_ollama_payload(monkeypatch, tmp_path):
    import httpx

    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "home"))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "qwen2.5:7b"}]}

    monkeypatch.setattr(httpx, "get", lambda url, headers=None, timeout=10: FakeResponse())
    from web.backend.routers.settings import ProviderFetchModelsRequest, fetch_provider_models

    response = fetch_provider_models(ProviderFetchModelsRequest(base_url="http://localhost:11434/v1"))
    assert [m["id"] for m in response["models"]] == ["qwen2.5:7b"]


def test_parse_provider_ref():
    from web.backend.deps import parse_provider_ref

    assert parse_provider_ref("deepseek::deepseek-chat") == ("deepseek", "deepseek-chat")
    assert parse_provider_ref("deepseek") == ("deepseek", None)
    assert parse_provider_ref("") == (None, None)
    assert parse_provider_ref(None) == (None, None)


def test_preference_validates_provider_ref(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("BOBODAN_HOME", str(home))
    catalog.upsert_provider("mine", {
        "type": "openai_compatible",
        "provider_name": "mine",
        "base_url": "https://example.com/v1",
        "api_key": "sk-abc",
        "model_default": "m1",
        "models": [{"id": "m1", "name": "M1"}],
    })
    config = ProviderFactory.load_config(_write_config(tmp_path, "llm:\n  default_provider: mine\n"))
    from service.preference_service import PreferenceService

    service = PreferenceService("mine", [])
    # 合法 `provider::model` 引用通过
    result = service.patch(0, {"ai": {"default_provider": "mine::m1"}}, {"mine"}, set())
    assert result["ai"]["default_provider"] == "mine::m1"
    # 未知供应商被拒绝
    with pytest.raises(ValueError):
        service.patch(1, {"ai": {"default_provider": "nope::m1"}}, {"mine"}, set())


def test_list_providers_keyless_ollama_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "home"))
    config = ProviderFactory.load_config(_write_config(tmp_path, "llm: {}\n"))
    result = AgentService.list_providers(config)
    ollama = next(item for item in result["providers"] if item["name"] == "ollama")
    assert ollama["configured"] is True


def test_session_model_name_roundtrip(tmp_path):
    from core.session import Session

    session = Session.new(str(tmp_path), max_messages=None)
    session.provider_name = "deepseek"
    session.model_name = "deepseek-chat"
    from service.agent_service import AgentService

    AgentService.save_session(session, str(tmp_path))
    loaded = AgentService.load_session(session.session_id, str(tmp_path))
    assert loaded["session"].provider_name == "deepseek"
    assert loaded["session"].model_name == "deepseek-chat"


def test_fetch_models_unauthorized(monkeypatch, tmp_path):
    import httpx

    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path / "home"))
    from web.backend.errors import APIError
    from web.backend.routers.settings import ProviderFetchModelsRequest, fetch_provider_models

    class FakeResponse:
        status_code = 401

        def raise_for_status(self):
            raise httpx.HTTPStatusError("401", request=None, response=self)

    monkeypatch.setattr(httpx, "get", lambda url, headers=None, timeout=10: FakeResponse())
    with pytest.raises(APIError) as exc_info:
        fetch_provider_models(ProviderFetchModelsRequest(base_url="https://example.com/v1", api_key="bad"))
    assert exc_info.value.code == "fetch_models_unauthorized"
