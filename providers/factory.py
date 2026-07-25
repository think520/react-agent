import logging
import os
import yaml
from .base import LLMProvider
from .deepseek import DeepseekProvider
from .minimax import MiniMaxProvider
from .openai_compat import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

KNOWN_PROVIDER_TYPES = {"deepseek", "minimax", "openai", "openai_compatible"}


class ProviderFactory:
    """Factory for creating LLM providers from config."""

    @staticmethod
    def _validate_provider_config(provider_type: str, provider_config: dict) -> None:
        """Validate provider config and raise clear errors."""
        if provider_type not in KNOWN_PROVIDER_TYPES:
            raise ValueError(
                f"Unknown provider type: '{provider_type}'. "
                f"Supported: {', '.join(sorted(KNOWN_PROVIDER_TYPES))}"
            )

        if "api_key_env" not in provider_config:
            raise ValueError(
                f"Provider '{provider_type}' is missing required field 'api_key_env' in config.yaml"
            )

        api_key_env = provider_config["api_key_env"]
        if not os.getenv(api_key_env):
            raise ValueError(
                f"Environment variable {api_key_env} is not set. "
                f"Add it to .env or export it before running."
            )

    @staticmethod
    def create(provider_config: dict, agent_config: dict) -> LLMProvider:
        provider_type = provider_config.get("type", "")
        ProviderFactory._validate_provider_config(provider_type, provider_config)

        api_key_env = provider_config["api_key_env"]
        api_key = os.getenv(api_key_env)

        if provider_type == "deepseek":
            return DeepseekProvider(
                api_key=api_key,
                model=provider_config.get("model", "deepseek-chat"),
                base_url=provider_config.get("base_url", "https://api.deepseek.com/v1"),
                temperature=agent_config.get("temperature", 0.7),
                timeout=agent_config.get("timeout", 60),
                max_retries=agent_config.get("max_retries", 3),
                provider_name="deepseek",
            )

        if provider_type == "minimax":
            return MiniMaxProvider(
                api_key=api_key,
                model=provider_config.get("model", "MiniMax-Text-01"),
                base_url=provider_config.get("base_url", "https://api.minimaxi.com/v1"),
                temperature=agent_config.get("temperature", 0.7),
                timeout=agent_config.get("timeout", 60),
                max_retries=agent_config.get("max_retries", 3),
            )

        if provider_type in {"openai", "openai_compatible"}:
            return OpenAICompatibleProvider(
                api_key=api_key,
                model=provider_config.get("model", "gpt-4"),
                base_url=provider_config.get("base_url", "https://api.openai.com/v1"),
                provider_name=provider_config.get("provider_name") or provider_type,
                temperature=agent_config.get("temperature", 0.7),
                timeout=agent_config.get("timeout", 60),
                max_retries=agent_config.get("max_retries", 3),
            )

        # Should never reach here due to validation, but just in case
        raise ValueError(f"Unknown provider type: {provider_type}")

    @staticmethod
    def load_config(config_path: str = "config.yaml") -> dict:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def create_from_config(config_path: str = "config.yaml") -> LLMProvider:
        config = ProviderFactory.load_config(config_path)
        llm_config = config.get("llm", {})
        default_provider = llm_config.get("default_provider", "")
        providers = llm_config.get("providers", {})

        if not default_provider:
            raise ValueError(
                "No 'default_provider' set under 'llm' in config.yaml. "
                f"Available providers: {', '.join(sorted(providers.keys())) or '(none)'}"
            )

        if default_provider not in providers:
            raise ValueError(
                f"Default provider '{default_provider}' not found in config.yaml. "
                f"Available: {', '.join(sorted(providers.keys()))}"
            )

        provider_config = providers[default_provider]
        agent_config = config.get("agent", {})

        provider = ProviderFactory.create(provider_config, agent_config)

        # Log config summary
        model = provider_config.get("model", "(default)")
        timeout = agent_config.get("timeout", 60)
        max_retries = agent_config.get("max_retries", 3)
        logger.info(
            f"[ProviderFactory] {default_provider} / {model} "
            f"(timeout={timeout}s, retries={max_retries})"
        )

        return provider
