from .openai_compat import OpenAICompatibleProvider


class DeepseekProvider(OpenAICompatibleProvider):
    """Deepseek LLM provider (OpenAI-compatible API)."""

    def __init__(self, api_key: str, model: str = "deepseek-chat",
                 base_url: str = "https://api.deepseek.com/v1",
                 temperature: float = 0.7, timeout: int = 60,
                 max_retries: int = 3, provider_name: str = "deepseek"):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider_name=provider_name,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )
