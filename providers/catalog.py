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
import re
from typing import Any
from urllib.parse import urlparse

from core.atomic_io import atomic_write_json
from rag.embedding_provider import PRESETS as EMBEDDING_PRESETS

_RERANK_MODEL_PATTERNS = (
    "rerank",
    "bge-reranker",
    "bce-reranker",
    "jina-reranker",
    "gte-rerank",
    "cohere-rerank",
)
_EMBEDDING_MODEL_PATTERNS = (
    "embedding",
    "bge-m3",
    "bge-large",
    "bge-base",
    "bge-small",
    "bce-embedding",
    "text-embedding",
    "nomic-embed",
    "mxbai-embed",
    "snowflake-arctic-embed",
    "multilingual-e5",
    "e5-large",
    "e5-base",
    "e5-small",
    "m3e-",
    "gte-large",
    "gte-base",
    "gte-qwen",
    "jina-embeddings",
)
_EMBED_WORD_RE = re.compile(r"(?:^|[^a-z0-9])embed(?:der)?(?:$|[^a-z0-9])")


def classify_model_kind(model_id: str) -> str:
    """Infer model capability kind ('chat' | 'embedding' | 'rerank') from model id."""
    lower = (model_id or "").strip().lower()
    if not lower:
        return "chat"
    if any(token in lower for token in _RERANK_MODEL_PATTERNS):
        return "rerank"
    if any(token in lower for token in _EMBEDDING_MODEL_PATTERNS) or _EMBED_WORD_RE.search(lower):
        return "embedding"
    return "chat"


_API_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/embeddings",
    "/completions",
    "/models",
)


def normalize_openai_base_url(url: str) -> tuple[str, bool]:
    """Trim whitespace/slashes and strip accidental OpenAI endpoint suffixes."""
    trimmed = (url or "").strip().rstrip("/")
    cleaned = trimmed
    changed = True
    while changed and cleaned:
        changed = False
        lower = cleaned.lower()
        for suffix in _API_ENDPOINT_SUFFIXES:
            if lower.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip("/")
                changed = True
                break
    return cleaned, bool(trimmed and cleaned != trimmed)


def _same_origin(url_a: str, url_b: str) -> bool:
    a = urlparse((url_a or "").strip())
    b = urlparse((url_b or "").strip())
    return bool(
        a.scheme and a.netloc and b.scheme and b.netloc
        and a.scheme.lower() == b.scheme.lower()
        and a.netloc.lower() == b.netloc.lower()
    )


def find_matching_provider_key(
    providers_cfg: dict[str, Any],
    base_url: str,
    preset: str = "",
) -> str:
    """Return API key from any configured provider sharing the same API origin."""
    target_url, _ = normalize_openai_base_url(base_url)
    if not target_url or not isinstance(providers_cfg, dict):
        return ""
    preset_clean = (preset or "").strip().lower()
    if preset_clean and isinstance(providers_cfg.get(preset_clean), dict):
        cand = providers_cfg[preset_clean]
        cand_url, _ = normalize_openai_base_url(str(cand.get("base_url") or ""))
        if _same_origin(target_url, cand_url):
            key = resolve_api_key(cand)
            if key:
                return key
    for cand in providers_cfg.values():
        if not isinstance(cand, dict):
            continue
        cand_url, _ = normalize_openai_base_url(str(cand.get("base_url") or ""))
        if _same_origin(target_url, cand_url):
            key = resolve_api_key(cand)
            if key:
                return key
    return ""


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
        "supports_embedding": False,
        "embedding_note": "DeepSeek 官方暂不提供向量 API，请搭配硅基流动等或本地 Ollama 做语义检索。",
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
        "supports_embedding": False,
        "embedding_note": "MiniMax 暂未内置标准向量接口，建议在「检索与 RAG」单独配置向量模型。",
    },
    "openai": {
        "type": "openai",
        "provider_name": "openai",
        "preset": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "model_default": "gpt-4o-mini",
        "models": [
            {"id": "gpt-4o-mini", "name": "GPT-4o mini"},
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"id": "text-embedding-3-small", "name": "Text Embedding 3 Small", "kind": "embedding"},
        ],
        "auth_type": "api-key",
        "supports_embedding": True,
    },
    "dashscope": {
        "type": "openai_compatible",
        "provider_name": "dashscope",
        "preset": "dashscope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "model_default": "qwen-plus",
        "models": [
            {"id": "qwen-plus", "name": "Qwen Plus"},
            {"id": "qwen-max", "name": "Qwen Max"},
            {"id": "text-embedding-v4", "name": "Text Embedding v4", "kind": "embedding"},
        ],
        "auth_type": "api-key",
        "supports_embedding": True,
    },
    "siliconflow": {
        "type": "openai_compatible",
        "provider_name": "siliconflow",
        "preset": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key_env": "SILICONFLOW_API_KEY",
        "model_default": "deepseek-ai/DeepSeek-V3",
        "models": [
            {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3"},
            {"id": "BAAI/bge-m3", "name": "BGE-M3（推荐向量）", "kind": "embedding"},
        ],
        "auth_type": "api-key",
        "supports_embedding": True,
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
        "models": [
            {"id": "glm-4-flash", "name": "GLM-4 Flash"},
            {"id": "glm-4-plus", "name": "GLM-4 Plus"},
            {"id": "embedding-3", "name": "Embedding-3", "kind": "embedding"},
        ],
        "auth_type": "api-key",
        "supports_embedding": True,
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
        "supports_embedding": True,
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
        "supports_embedding": True,
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
        "supports_embedding": True,
        "note": "本地 vLLM（免 key；别和 Bobodan 的 8000 端口冲突）",
    },
}

_CATALOG_FILE = "provider.json"
VALID_MODEL_KINDS = frozenset({"chat", "embedding", "rerank"})
VALID_EMBEDDING_MODES = frozenset({"auto", "provider", "custom", "ollama", "disabled"})

DEFAULT_EMBEDDING_CONFIG: dict[str, Any] = {
    "mode": "auto",
    "provider_name": "",
    "preset": "",
    "base_url": "",
    "model": "",
    "api_key": "",
    "dim": None,
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen3-embedding:0.6b",
}


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


def _normalize_models(raw_models: Any) -> list[dict[str, str]]:
    if not isinstance(raw_models, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        model_name = str(item.get("name") or model_id).strip() or model_id
        normalized_item: dict[str, str] = {"id": model_id, "name": model_name}
        kind = str(item.get("kind") or "").strip().lower()
        if kind in VALID_MODEL_KINDS:
            normalized_item["kind"] = kind
        result.append(normalized_item)
    return result


def _normalize_provider(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """把任意来源的 provider 配置规整为 catalog 条目。"""
    model = raw.get("model") or raw.get("model_default") or ""
    models = _normalize_models(raw.get("models"))
    if not models and model:
        models = [{"id": model, "name": model}]
    # auth_type 语义借自 openhanako：api-key（必须）/ optional（可空）/ none（本地免 key）。
    keyless = bool(raw.get("keyless"))
    auth_type = raw.get("auth_type") or ("none" if keyless else "api-key")
    if auth_type not in {"api-key", "optional", "none"}:
        auth_type = "api-key"
    entry: dict[str, Any] = {
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
    if "supports_embedding" in raw:
        entry["supports_embedding"] = bool(raw["supports_embedding"])
    if raw.get("embedding_note"):
        entry["embedding_note"] = str(raw["embedding_note"])
    return entry


def load_catalog() -> dict[str, Any]:
    """读取 provider.json；不存在返回空目录。"""
    try:
        with open(catalog_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or not isinstance(data.get("providers"), dict):
            return {"version": 1, "providers": {}}
        result: dict[str, Any] = {
            "version": int(data.get("version") or 1),
            "providers": data.get("providers", {}),
        }
        if isinstance(data.get("embedding"), dict):
            result["embedding"] = dict(data["embedding"])
        return result
    except (OSError, ValueError):
        return {"version": 1, "providers": {}}


def save_catalog(catalog: dict[str, Any]) -> None:
    """写回 provider.json（含密钥）。目录不存在时创建。"""
    directory = resolve_home()
    os.makedirs(directory, exist_ok=True)
    payload: dict[str, Any] = {"version": 1, "providers": catalog.get("providers", {})}
    if isinstance(catalog.get("embedding"), dict) and catalog["embedding"]:
        payload["embedding"] = catalog["embedding"]
    atomic_write_json(catalog_path(), payload)


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
    if entry.get("base_url"):
        cleaned_url, _ = normalize_openai_base_url(str(entry.get("base_url") or ""))
        entry = {**entry, "base_url": cleaned_url}
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


def _normalize_saved_custom(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    api_key = str(raw.get("api_key") or "").strip()
    if not api_key:
        return None
    cleaned_url, _ = normalize_openai_base_url(str(raw.get("base_url") or ""))
    dim_raw = raw.get("dim")
    dim = int(dim_raw) if dim_raw not in (None, "", 0, "0") else None
    if dim is not None and dim <= 0:
        dim = None
    return {
        "preset": str(raw.get("preset") or "").strip().lower(),
        "base_url": cleaned_url,
        "model": str(raw.get("model") or "").strip(),
        "api_key": api_key,
        "dim": dim,
    }


def _normalize_embedding(raw: dict[str, Any]) -> dict[str, Any]:
    mode = str(raw.get("mode") or "auto").strip().lower()
    if mode not in VALID_EMBEDDING_MODES:
        raise ValueError(f"Unsupported embedding mode: {mode!r}")
    dim_raw = raw.get("dim")
    dim = int(dim_raw) if dim_raw not in (None, "", 0, "0") else None
    if dim is not None and dim <= 0:
        dim = None
    cleaned_url, _ = normalize_openai_base_url(str(raw.get("base_url") or ""))
    normalized: dict[str, Any] = {
        "mode": mode,
        "provider_name": str(raw.get("provider_name") or "").strip(),
        "preset": str(raw.get("preset") or "").strip().lower(),
        "base_url": cleaned_url,
        "model": str(raw.get("model") or "").strip(),
        "api_key": str(raw.get("api_key") or "").strip(),
        "dim": dim,
        "ollama_url": str(raw.get("ollama_url") or "http://localhost:11434").strip() or "http://localhost:11434",
        "ollama_model": str(raw.get("ollama_model") or "qwen3-embedding:0.6b").strip() or "qwen3-embedding:0.6b",
    }
    saved_custom = _normalize_saved_custom(raw.get("saved_custom"))
    if saved_custom:
        normalized["saved_custom"] = saved_custom
    return normalized


def _effective_custom_url(entry: dict[str, Any]) -> str:
    base_url = str(entry.get("base_url") or "").strip()
    if base_url:
        return base_url
    preset = str(entry.get("preset") or "").strip().lower()
    return str(EMBEDDING_PRESETS.get(preset, {}).get("base_url") or "").strip()


def get_embedding_config() -> dict[str, Any]:
    """Read user-saved embedding config from ~/.bobodan/provider.json without creating it."""
    raw = load_catalog().get("embedding")
    if not isinstance(raw, dict) or not raw:
        return {}
    try:
        return _normalize_embedding(raw)
    except ValueError:
        return {}


def save_embedding_config(entry: dict[str, Any], *, clear_api_key: bool = False) -> dict[str, Any]:
    """Persist embedding configuration in provider.json while keeping keys safe across mode switches."""
    catalog = _ensure_catalog()
    normalized = _normalize_embedding(entry)
    existing = catalog.get("embedding") if isinstance(catalog.get("embedding"), dict) else {}
    existing_saved_custom = _normalize_saved_custom(existing.get("saved_custom")) if existing else None
    if not existing_saved_custom and existing and existing.get("api_key"):
        existing_saved_custom = _normalize_saved_custom(existing)

    if clear_api_key:
        normalized["api_key"] = ""
        normalized.pop("saved_custom", None)
    elif normalized["mode"] == "custom":
        next_url = _effective_custom_url(normalized)
        if not normalized["api_key"]:
            for candidate in (existing, existing_saved_custom):
                if not candidate or not candidate.get("api_key"):
                    continue
                if _same_origin(_effective_custom_url(candidate), next_url):
                    normalized["api_key"] = str(candidate["api_key"])
                    break
        if normalized["api_key"]:
            normalized["saved_custom"] = {
                "preset": normalized["preset"],
                "base_url": normalized["base_url"],
                "model": normalized["model"],
                "api_key": normalized["api_key"],
                "dim": normalized["dim"],
            }
        else:
            normalized.pop("saved_custom", None)
    else:
        # Preserve previous cloud key across temporary switches (e.g. disabled / ollama / provider).
        if existing_saved_custom:
            normalized["saved_custom"] = existing_saved_custom
    catalog["embedding"] = normalized
    save_catalog(catalog)
    return dict(normalized)


def _strip_v1_suffix(url: str) -> str:
    clean = (url or "").strip().rstrip("/")
    if clean.lower().endswith("/v1"):
        clean = clean[:-3].rstrip("/")
    return clean or "http://localhost:11434"


def apply_to_config(config: dict[str, Any]) -> dict[str, Any]:
    """把 catalog 合并进 config，返回新 dict（不修改原对象）。

    合并后 `config["llm"]["providers"]` 是 UI 管理的真相，且保留
    `model` 字段（= model_default）以兼容现有 factory / 服务代码；
    若 `provider.json` 含 `embedding` 节，则同步覆盖 `config["rag"]` 向量配置。
    """
    merged = {
        **config,
        "llm": {**config.get("llm", {})},
        "rag": {**(config.get("rag") or {})},
    }
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

    embedding_cfg = get_embedding_config()
    rag = merged["rag"]
    if embedding_cfg:
        mode = embedding_cfg.get("mode", "auto")
        if mode == "disabled":
            rag["embedding_backend"] = "disabled"
        elif mode == "ollama":
            rag["embedding_backend"] = "ollama"
            rag["ollama_url"] = embedding_cfg.get("ollama_url") or "http://localhost:11434"
            rag["ollama_model"] = embedding_cfg.get("ollama_model") or "qwen3-embedding:0.6b"
        elif mode == "provider":
            pname = embedding_cfg.get("provider_name") or ""
            provider_cfg = normalized.get(pname)
            if provider_cfg and (pname == "ollama" or provider_cfg.get("preset") == "ollama"):
                rag["embedding_backend"] = "ollama"
                rag["ollama_url"] = _strip_v1_suffix(provider_cfg.get("base_url") or "")
                rag["ollama_model"] = embedding_cfg.get("model") or "qwen3-embedding:0.6b"
            elif provider_cfg:
                preset = str(provider_cfg.get("preset") or "").strip().lower()
                if preset not in EMBEDDING_PRESETS:
                    preset = pname.lower() if pname.lower() in EMBEDDING_PRESETS else ""
                model = embedding_cfg.get("model") or str(EMBEDDING_PRESETS.get(preset, {}).get("model") or "")
                rag["embedding_backend"] = "openai_compat"
                rag["embedding_preset"] = preset
                rag["embedding_base_url"] = str(provider_cfg.get("base_url") or "")
                rag["embedding_model"] = model
                rag["embedding_api_key_env"] = str(provider_cfg.get("api_key_env") or "")
                rag["embedding_api_key"] = resolve_api_key(provider_cfg)
                rag["embedding_dim"] = int(embedding_cfg["dim"]) if embedding_cfg.get("dim") else 0
            else:
                rag["embedding_backend"] = "openai_compat"
                rag["embedding_preset"] = ""
                rag["embedding_base_url"] = ""
                rag["embedding_model"] = embedding_cfg.get("model") or ""
                rag["embedding_api_key_env"] = ""
                rag["embedding_api_key"] = ""
                rag["embedding_dim"] = 0
        elif mode == "custom":
            preset = str(embedding_cfg.get("preset") or "").strip().lower()
            preset_meta = EMBEDDING_PRESETS.get(preset, {})
            base_url = embedding_cfg.get("base_url") or str(preset_meta.get("base_url") or "")
            model = embedding_cfg.get("model") or str(preset_meta.get("model") or "")
            key = str(embedding_cfg.get("api_key") or "").strip()
            key_env = str(preset_meta.get("api_key_env") or "")
            if not key:
                key = find_matching_provider_key(normalized, base_url, preset=preset)
            rag["embedding_backend"] = "openai_compat"
            rag["embedding_preset"] = preset
            rag["embedding_base_url"] = base_url
            rag["embedding_model"] = model
            rag["embedding_api_key_env"] = key_env
            rag["embedding_api_key"] = key
            rag["embedding_dim"] = int(embedding_cfg["dim"]) if embedding_cfg.get("dim") else 0

    if not embedding_cfg or embedding_cfg.get("mode", "auto") == "auto":
        # Auto mode preserves legacy env-var behavior, and also lets users who already
        # entered a matching provider key in UI (`siliconflow`, `zhipu`, etc.) reuse it.
        if str(rag.get("embedding_backend", "auto") or "auto").strip().lower() == "auto":
            preset = str(rag.get("embedding_preset") or "").strip().lower()
            preset_meta = EMBEDDING_PRESETS.get(preset, {})
            key_env = str(rag.get("embedding_api_key_env") or preset_meta.get("api_key_env") or "")
            has_env_key = bool(key_env and os.getenv(key_env, "").strip())
            if preset == "zhipu" and not has_env_key:
                has_env_key = bool(os.getenv("ZHIPU_API_KEY", "").strip() or os.getenv("ZHIPUAI_API_KEY", "").strip())
            if not rag.get("embedding_api_key") and not has_env_key and preset in normalized:
                candidate = normalized[preset]
                target_url = str(rag.get("embedding_base_url") or preset_meta.get("base_url") or "")
                if _same_origin(target_url, str(candidate.get("base_url") or "")):
                    reused = resolve_api_key(candidate)
                    if reused:
                        rag["embedding_api_key"] = reused
    return merged


def resolve_api_key(provider_config: dict[str, Any]) -> str:
    """api_key 为空时回退 api_key_env 环境变量（迁移兼容层）。"""
    api_key = provider_config.get("api_key")
    if not api_key:
        api_key_env = provider_config.get("api_key_env", "")
        if api_key_env:
            api_key = os.getenv(api_key_env, "")
        if not api_key and api_key_env in {"ZHIPUAI_API_KEY", "ZHIPU_API_KEY"}:
            alt_env = "ZHIPU_API_KEY" if api_key_env == "ZHIPUAI_API_KEY" else "ZHIPUAI_API_KEY"
            api_key = os.getenv(alt_env, "")
    return api_key or ""
