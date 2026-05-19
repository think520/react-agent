from providers.deepseek import DeepseekProvider
from providers.openai_compat import OpenAICompatibleProvider


def test_deepseek_provider_init():
    provider = DeepseekProvider(api_key="test-key")
    assert provider.get_name() == "deepseek"
    assert isinstance(provider, OpenAICompatibleProvider)


def test_deepseek_provider_complete():
    provider = DeepseekProvider(api_key="test-key")
    messages = [{"role": "user", "content": "hello"}]
    payload = provider._build_payload(messages, tools=[])

    assert payload["model"] == "deepseek-chat"
    assert payload["messages"] == messages
    assert payload["temperature"] == 0.7
    assert "stream" not in payload
