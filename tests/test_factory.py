import os
from providers.factory import ProviderFactory
from providers.openai_compat import OpenAICompatibleProvider
from providers.deepseek import DeepseekProvider


def test_factory_load_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
llm:
  default_provider: deepseek
  providers:
    deepseek:
      type: deepseek
      api_key_env: TEST_KEY
      model: test-model
agent:
  temperature: 0.7
""",
        encoding="utf-8",
    )
    os.environ["TEST_KEY"] = "test-api-key"
    config = ProviderFactory.load_config(str(config_file))
    assert config["llm"]["default_provider"] == "deepseek"


def test_factory_create_openai_provider_uses_openai_compat(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    provider = ProviderFactory.create(
        {
            "type": "openai",
            "api_key_env": "OPENAI_API_KEY",
            "model": "gpt-4",
            "base_url": "https://api.openai.com/v1",
        },
        {"temperature": 0.1, "timeout": 30, "max_retries": 1},
    )

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.get_name() == "openai"


def test_factory_create_deepseek_provider(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider = ProviderFactory.create(
        {
            "type": "deepseek",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
        },
        {"temperature": 0.7, "timeout": 60, "max_retries": 3},
    )

    assert isinstance(provider, DeepseekProvider)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.get_name() == "deepseek"


def test_factory_missing_env_var_raises():
    try:
        ProviderFactory.create(
            {"type": "minimax", "api_key_env": "MISSING_MINIMAX_KEY"},
            {},
        )
    except ValueError as error:
        assert "MISSING_MINIMAX_KEY" in str(error)
    else:
        raise AssertionError("Expected ValueError for missing env var")


def test_factory_unknown_provider_type_raises():
    try:
        ProviderFactory.create(
            {"type": "nonexistent"},
            {},
        )
    except ValueError as error:
        assert "nonexistent" in str(error)
    else:
        raise AssertionError("Expected ValueError for unknown provider type")
