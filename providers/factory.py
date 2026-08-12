import logging
import yaml
from .base import LLMProvider
from .deepseek import DeepseekProvider
from .minimax import MiniMaxProvider
from .openai_compat import OpenAICompatibleProvider
from .errors import ProviderConfigError

logger = logging.getLogger(__name__)

KNOWN_PROVIDER_TYPES = {"deepseek", "minimax", "openai", "openai_compatible"}


def _common(provider_config: dict, agent_config: dict) -> dict:
    from providers.catalog import resolve_api_key

    return {
        "api_key": resolve_api_key(provider_config),
        "model": provider_config.get("model"),
        "base_url": provider_config.get("base_url"),
        "temperature": agent_config.get("temperature", 0.7),
        "timeout": agent_config.get("timeout", 60),
        "max_retries": agent_config.get("max_retries", 3),
    }


def _build_deepseek(provider_config: dict, agent_config: dict) -> LLMProvider:
    values = _common(provider_config, agent_config)
    return DeepseekProvider(
        **{**values, "model": values["model"] or "deepseek-chat", "base_url": values["base_url"] or "https://api.deepseek.com/v1"},
        provider_name="deepseek",
    )


def _build_minimax(provider_config: dict, agent_config: dict) -> LLMProvider:
    values = _common(provider_config, agent_config)
    return MiniMaxProvider(
        **{**values, "model": values["model"] or "MiniMax-Text-01", "base_url": values["base_url"] or "https://api.minimaxi.com/v1"},
    )


def _build_openai(provider_config: dict, agent_config: dict) -> LLMProvider:
    values = _common(provider_config, agent_config)
    return OpenAICompatibleProvider(
        **{**values, "model": values["model"] or "gpt-4", "base_url": values["base_url"] or "https://api.openai.com/v1"},
        provider_name=provider_config.get("provider_name") or provider_config.get("type") or "openai",
    )


_PROVIDER_BUILDERS = {
    "deepseek": _build_deepseek,
    "minimax": _build_minimax,
    "openai": _build_openai,
    "openai_compatible": _build_openai,
}


class ProviderFactory:
    """Factory for creating LLM providers from config."""

    @staticmethod
    def _validate_provider_config(provider_type: str, provider_config: dict) -> None:
        """Validate provider config and raise clear errors."""
        if provider_type not in KNOWN_PROVIDER_TYPES:
            raise ProviderConfigError(
                f"Unknown provider type: '{provider_type}'. "
                f"Supported: {', '.join(sorted(KNOWN_PROVIDER_TYPES))}"
            )

        from providers.catalog import resolve_api_key

        if not resolve_api_key(provider_config):
            api_key_env = provider_config.get("api_key_env", "")
            hint = (
                f"Environment variable {api_key_env} is not set."
                if api_key_env
                else "No API key configured."
            )
            raise ProviderConfigError(
                f"Provider '{provider_type}' has no API key. "
                f"{hint} Set it in Settings → AI & Models."
            )

    @staticmethod
    def create(provider_config: dict, agent_config: dict, model: str | None = None) -> LLMProvider:
        provider_type = provider_config.get("type", "")
        ProviderFactory._validate_provider_config(provider_type, provider_config)

        builder_config = dict(provider_config)
        if model:
            builder_config["model"] = model
        return _PROVIDER_BUILDERS[provider_type](builder_config, agent_config)

    @staticmethod
    def load_config(config_path: str = "config.yaml") -> dict:
        """Load config.yaml and merge the provider catalog (P5G.4).

        `~/.bobodan/provider.json` overrides `llm.providers`; built-in
        presets fill gaps; first run migrates legacy providers. Side
        effect: migration may write the catalog file once.
        """
        from providers.catalog import apply_to_config

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return apply_to_config(config)

    @staticmethod
    def create_from_config(config_path: str = "config.yaml") -> LLMProvider:
        config = ProviderFactory.load_config(config_path)
        llm_config = config.get("llm", {})
        default_provider = llm_config.get("default_provider", "")
        providers = llm_config.get("providers", {})

        if not default_provider:
            raise ProviderConfigError(
                "No 'default_provider' set under 'llm' in config.yaml. "
                f"Available providers: {', '.join(sorted(providers.keys())) or '(none)'}"
            )

        if default_provider not in providers:
            raise ProviderConfigError(
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
