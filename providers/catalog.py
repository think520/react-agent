"""Provider catalog — user-editable model provider configuration.

真相源 `~/.bobodan/provider.json`（P5G.4）。用户在设置页管理供应商（API key、
base_url、模型列表），不再需要手改 `config.yaml` 或 `.env`。

v1 schema::

    {
      "version": 1,
      "providers": {
        "deepseek": {
          "type": "openai_compatible",      # deepseek | minimax | openai | openai_compatible
          "provider_name": "deepseek",       # openai_compatible 自定义时的别名
          "preset": "deepseek",              # 内建模板 id；自定义为空
          "base_url": "https://api.deepseek.com/v1",
          "api_key": "sk-...",               # 可为空 → 回退 api_key_env 环境变量
          "api_key_env": "DEEPSEEK_API_KEY", # 迁移保留的旧字段
          "model_default": "deepseek-chat",  # 该供应商的默认模型
          "models": [                        # 供应商下挂的模型列表
            {"id": "deepseek-chat", "name": "DeepSeek Chat"}
          ]
        }
      }
    }

解析优先级：provider.json → config.yaml `llm.providers`（首次启动自动迁移）→
内建模板（仅补齐，不写入文件）。
"""

from __future__ import annotations

import json
import os
from typing import Any

BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "type": "deepseek",
        "provider_name": "deepseek",
        "preset": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_default": "deepseek-chat",
        "models": [{"id": "deepseek-chat", "name": "DeepSeek Chat"}, {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner"}],
        "auth_type": "api-key",
    },
    "minimax": {
        "type": "minimax",
        "provider_name": "minimax",
        "preset": "minimax",
        "base_url": "https://api.minimaxi.com/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "model_default": "MiniMax-Text-01",
        "models": [{"id": "MiniMax-Text-01", "name": "MiniMax Text"}],
        "auth_type": "api-key",
    },
    "openai": {
        "type": "openai",
        "provider_name": "openai",
        "preset": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "model_default": "gpt-4o-mini",
        "models": [{"id": "gpt-4o-mini", "name": "GPT-4o mini"}, {"id": "gpt-4o", "name": "GPT-4o"}],
        "auth_type": "api-key",
    },
    "dashscope": {
        "type": "openai_compatible",
        "provider_name": "dashscope",
        "preset": "dashscope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "model_default": "qwen-plus",
        "models": [{"id": "qwen-plus", "name": "Qwen Plus"}, {"id": "qwen-max", "name": "Qwen Max"}],
        "auth_type": "api-key",
    },
    "siliconflow": {
        "type": "openai_compatible",
        "provider_name": "siliconflow",
        "preset": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key_env": "SILICONFLOW_API_KEY",
        "model_default": "deepseek-ai/DeepSeek-V3",
        "models": [{"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3"}],
        "auth_type": "api-key",
    },
    "openrouter": {
        "type": "openai_compatible",
        "provider_name": "openrouter",
        "preset": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model_default": "deepseek/deepseek-chat",
        "models": [{"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat"}],
        "auth_type": "api-key",
    },
    "kimi": {
        "type": "openai_compatible",
        "provider_name": "kimi",
        "preset": "kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "model_default": "moonshot-v1-8k",
        "models": [{"id": "moonshot-v1-8k", "name": "Moonshot v1 8K"}, {"id": "moonshot-v1-32k", "name": "Moonshot v1 32K"}],
        "auth_type": "api-key",
        "note": "Kimi（Moonshot AI）",
    },
    "zhipu": {
        "type": "openai_compatible",
        "provider_name": "zhipu",
        "preset": "zhipu",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPUAI_API_KEY",
        "model_default": "glm-4-flash",
        "models": [{"id": "glm-4-flash", "name": "GLM-4 Flash"}, {"id": "glm-4-plus", "name": "GLM-4 Plus"}],
        "auth_type": "api-key",
        "note": "智谱 GLM",
    },
    "gemini": {
        "type": "openai_compatible",
        "provider_name": "gemini",
        "preset": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model_default": "gemini-2.0-flash",
        "models": [{"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash"}, {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"}],
        "auth_type": "api-key",
        "note": "Google AI Studio 的 OpenAI 兼容端点",
    },
    "xai": {
        "type": "openai_compatible",
        "provider_name": "xai",
        "preset": "xai",
        "base_url": "https://api.x.ai/v1",
        "api_key_env": "XAI_API_KEY",
        "model_default": "grok-3",
        "models": [{"id": "grok-3", "name": "Grok 3"}, {"id": "grok-3-mini", "name": "Grok 3 mini"}],
        "auth_type": "api-key",
        "note": "xAI Grok",
    },
    "mistral": {
        "type": "openai_compatible",
        "provider_name": "mistral",
        "preset": "mistral",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "model_default": "mistral-large-latest",
        "models": [{"id": "mistral-large-latest", "name": "Mistral Large"}, {"id": "mistral-small-latest", "name": "Mistral Small"}],
        "auth_type": "api-key",
    },
    "groq": {
        "type": "openai_compatible",
        "provider_name": "groq",
        "preset": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model_default": "llama-3.3-70b-versatile",
        "models": [{"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B"}],
        "auth_type": "api-key",
    },
    "together": {
        "type": "openai_compatible",
        "provider_name": "together",
        "preset": "together",
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": "TOGETHER_API_KEY",
        "model_default": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "models": [{"id": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "name": "Llama 3.3 70B Turbo"}],
        "auth_type": "api-key",
    },
    "nvidia": {
        "type": "openai_compatible",
        "provider_name": "nvidia",
        "preset": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model_default": "deepseek-ai/deepseek-r1",
        "models": [{"id": "deepseek-ai/deepseek-r1", "name": "DeepSeek R1 (NIM)"}],
        "auth_type": "api-key",
    },
    "ollama": {
        "type": "openai_compatible",
        "provider_name": "ollama",
        "preset": "ollama",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "",
        "model_default": "",
        "models": [],
        "auth_type": "none",
        "keyless": True,
        "note": "本地 Ollama（免 key）",
    },
    "lmstudio": {
        "type": "openai_compatible",
        "provider_name": "lmstudio",
        "preset": "lmstudio",
        "base_url": "http://localhost:1234/v1",
        "api_key_env": "",
        "model_default": "",
        "models": [],
        "auth_type": "none",
        "keyless": True,
        "note": "本地 LM Studio（免 key）",
    },
    "vllm": {
        "type": "openai_compatible",
        "provider_name": "vllm",
        "preset": "vllm",
        "base_url": "http://localhost:8000/v1",
        "api_key_env": "",
        "model_default": "",
        "models": [],
        "auth_type": "none",
        "keyless": True,
        "note": "本地 vLLM（免 key；别和 Bobodan 的 8000 端口冲突）",
    },
}

_CATALOG_FILE = "provider.json"


def resolve_home() -> str:
    """应用数据根目录 ~/.bobodan（web / CLI / Electron 共享）。

    与 cli/web_serve.resolve_home 保持同一约定：BOBODAN_HOME 可覆盖
    （Electron 与测试隔离使用）。
    """
    configured = os.getenv("BOBODAN_HOME")
    if configured:
        return os.path.abspath(configured)
    return os.path.expanduser("~/.bobodan")


def catalog_path() -> str:
    return os.path.join(resolve_home(), _CATALOG_FILE)


def _normalize_provider(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """把任意来源的 provider 配置规整为 catalog 条目。"""
    model = raw.get("model") or raw.get("model_default") or ""
    models = raw.get("models")
    if not models and model:
        models = [{"id": model, "name": model}]
    # auth_type 语义借自 openhanako：api-key（必须）/ optional（可空）/ none（本地免 key）。
    keyless = bool(raw.get("keyless"))
    auth_type = raw.get("auth_type") or ("none" if keyless else "api-key")
    if auth_type not in {"api-key", "optional", "none"}:
        auth_type = "api-key"
    entry = {
        "auth_type": auth_type,
        "type": raw.get("type", "openai_compatible"),
        "provider_name": raw.get("provider_name") or raw.get("preset") or name,
        "base_url": raw.get("base_url", ""),
        "api_key": raw.get("api_key", ""),
        "api_key_env": raw.get("api_key_env", ""),
        "model_default": raw.get("model_default") or model,
        "models": models or [],
    }
    preset = raw.get("preset")
    if preset:
        entry["preset"] = preset
    if raw.get("keyless"):
        entry["keyless"] = True
    return entry


def load_catalog() -> dict[str, Any]:
    """读取 provider.json；不存在返回空目录。"""
    try:
        with open(catalog_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or not isinstance(data.get("providers"), dict):
            return {"version": 1, "providers": {}}
        return data
    except (OSError, ValueError):
        return {"version": 1, "providers": {}}


def save_catalog(catalog: dict[str, Any]) -> None:
    """写回 provider.json（含密钥）。目录不存在时创建。"""
    directory = resolve_home()
    os.makedirs(directory, exist_ok=True)
    payload = {"version": 1, "providers": catalog.get("providers", {})}
    with open(catalog_path(), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def migrate_from_config(config: dict[str, Any]) -> bool:
    """首次启动迁移 config.yaml 的 llm.providers 到 provider.json。

    保留 api_key_env，用户在 UI 补填 key 后自然覆盖（零断供过渡）。
    迁移时补齐内建模板中缺失的条目（如 ollama），老用户无需手动添加。
    返回是否执行了迁移。
    """
    if os.path.exists(catalog_path()):
        return False
    legacy = (config.get("llm") or {}).get("providers") or {}
    if not legacy:
        return False
    providers = {
        name: _normalize_provider(name, raw)
        for name, raw in legacy.items()
        if isinstance(raw, dict)
    }
    for name, preset in BUILTIN_PRESETS.items():
        providers.setdefault(name, dict(preset))
    save_catalog({"version": 1, "providers": providers})
    return True


def resolve_providers(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """合并后的 providers 真相：provider.json 优先，内建模板只兜全新安装。

    文件一旦存在（迁移或首次 UI 写入），完全以文件为准——用户删除的
    模板不会自动复活。返回 name → 规整后的 provider 配置。
    """
    migrate_from_config(config)
    if os.path.exists(catalog_path()):
        return dict(load_catalog().get("providers", {}))
    return {name: dict(raw) for name, raw in BUILTIN_PRESETS.items()}


def _ensure_catalog() -> dict[str, Any]:
    """读取文件；文件不存在时以模板为基底（首次 UI 写入后文件存在，
    模板补齐语义失效，以文件为准）。"""
    catalog = load_catalog()
    if not os.path.exists(catalog_path()):
        catalog["providers"] = {name: dict(raw) for name, raw in BUILTIN_PRESETS.items()}
    return catalog


def upsert_provider(name: str, entry: dict[str, Any]) -> None:
    """新增或编辑一个供应商并写盘。不存在的旧条目保留。

    api_key 为空且该供应商已存在时保留原 key（编辑表单留空 = 不改密钥）。
    """
    catalog = _ensure_catalog()
    # 从模板添加时继承模板的 auth_type / keyless / api_key_env —— 否则本地服务
    # （ollama / lmstudio / vllm）保存一次就会丢掉「免 key」语义。
    preset = entry.get("preset") or name
    preset_entry = BUILTIN_PRESETS.get(preset)
    if preset_entry:
        merged = dict(preset_entry)
        merged.update({key: value for key, value in entry.items() if value not in (None, "")})
        merged.setdefault("preset", preset)
        entry = merged
    normalized = _normalize_provider(name, entry)
    existing = catalog["providers"].get(name)
    if existing and not normalized.get("api_key"):
        normalized["api_key"] = existing.get("api_key", "")
    catalog["providers"][name] = normalized
    save_catalog(catalog)


def delete_provider(name: str) -> bool:
    """删除一个供应商。返回是否删除成功（未知名称返回 False）。"""
    catalog = _ensure_catalog()
    if name not in catalog["providers"]:
        return False
    del catalog["providers"][name]
    save_catalog(catalog)
    return True


def apply_to_config(config: dict[str, Any]) -> dict[str, Any]:
    """把 catalog 合并进 config，返回新 dict（不修改原对象）。

    合并后 `config["llm"]["providers"]` 是 UI 管理的真相，且保留
    `model` 字段（= model_default）以兼容现有 factory / 服务代码。
    """
    merged = {**config, "llm": {**config.get("llm", {})}}
    providers = resolve_providers(config)
    normalized: dict[str, dict[str, Any]] = {}
    for name, raw in providers.items():
        entry = dict(raw)
        # 兼容字段：现有代码读 provider["model"]（如 factory 的默认模型）
        entry["model"] = entry.get("model_default") or ""
        # 空模型列表的服务（如未拉取的 ollama）用默认模型兜底
        models = entry.get("models") or []
        if not models and entry["model"]:
            models = [{"id": entry["model"], "name": entry["model"]}]
        entry["models"] = models
        normalized[name] = entry
    merged["llm"]["providers"] = normalized
    return merged


def resolve_api_key(provider_config: dict[str, Any]) -> str:
    """api_key 为空时回退 api_key_env 环境变量（迁移兼容层）。"""
    api_key = provider_config.get("api_key")
    if not api_key:
        api_key_env = provider_config.get("api_key_env", "")
        if api_key_env:
            api_key = os.getenv(api_key_env, "")
    return api_key or ""
