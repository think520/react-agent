"""Service layer for RAG embedding configuration, diagnostics, backfill, and hit testing."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any
from urllib.parse import urlparse

import httpx

from core.cancellation import CancelToken
from knowledge.paths import knowledge_dir
from providers.catalog import (
    BUILTIN_PRESETS,
    classify_model_kind,
    find_matching_provider_key,
    get_embedding_config,
    normalize_openai_base_url,
    resolve_api_key,
)
from rag.embedding_provider import (
    PRESETS as EMBEDDING_PRESETS,
    OllamaEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    create_embedding_provider,
)
from rag.embedding_service import EmbeddingService
from rag.embedding_signature import mismatch_reason, read_signature, write_signature
from rag.hybrid import classify_vector_error
from rag.qdrant_store import close_shared_qdrant_store, shared_qdrant_store
from rag.retrieval_status import (
    NO_VECTORS,
    NOT_CONFIGURED,
    OK,
    PROVIDER_UNAVAILABLE,
    SIGNATURE_MISMATCH,
    VECTOR_STORE_LOCKED,
    build_semantic_status,
    redact_secrets,
)
from rag.retriever import clear_retrieval_cache
from rag.sqlite_store import KBSQLiteStore
from service.agent_service import AgentService
from service.kb_service import KBService

logger = logging.getLogger(__name__)

EMBEDDING_PRESET_UI: dict[str, dict[str, Any]] = {
    "siliconflow": {
        "id": "siliconflow",
        "label": "硅基流动（SiliconFlow）",
        "badge": "推荐 · BGE-M3 免费可用",
        "description": "个人学习友好，支持 BAAI/bge-m3 与 Qwen3-Embedding，可与对话共用同一把硅基流动 Key。",
        "suggested_models": ["BAAI/bge-m3", "BAAI/bge-large-zh-v1.5", "Qwen/Qwen3-Embedding-8B"],
    },
    "dashscope": {
        "id": "dashscope",
        "label": "阿里云百炼（DashScope）",
        "badge": "国内稳定",
        "description": "使用阿里云百炼 OpenAI 兼容接口（text-embedding-v4），可与 Qwen 对话共用百炼 Key。",
        "suggested_models": ["text-embedding-v4", "text-embedding-v3"],
    },
    "zhipu": {
        "id": "zhipu",
        "label": "智谱 AI（Zhipu）",
        "badge": "2048 维",
        "description": "使用智谱 OpenAI 兼容接口（embedding-3），可与 GLM 对话共用智谱 Key。",
        "suggested_models": ["embedding-3", "embedding-2"],
    },
    "openai": {
        "id": "openai",
        "label": "OpenAI",
        "badge": "通用",
        "description": "OpenAI 官方 text-embedding-3-small / large，需可直连或通过兼容端点访问。",
        "suggested_models": ["text-embedding-3-small", "text-embedding-3-large"],
    },
    "custom": {
        "id": "custom",
        "label": "自定义 OpenAI 兼容",
        "badge": "任意兼容接口",
        "description": "适用于 OneAPI / NewAPI / 阿里云 / 私有网关，填写根路径（如 https://example.com/v1）、模型名与密钥。",
        "suggested_models": [],
    },
}


def _same_origin(url_a: str, url_b: str) -> bool:
    a = urlparse((url_a or "").strip())
    b = urlparse((url_b or "").strip())
    return bool(
        a.scheme and a.netloc and b.scheme and b.netloc
        and a.scheme.lower() == b.scheme.lower()
        and a.netloc.lower() == b.netloc.lower()
    )


def _strip_v1_suffix(url: str) -> str:
    clean = (url or "").strip().rstrip("/")
    if clean.lower().endswith("/v1"):
        clean = clean[:-3].rstrip("/")
    return clean or "http://localhost:11434"


_DOC_EXTENSIONS = (".markdown", ".md", ".pdf", ".docx", ".pptx", ".txt", ".html", ".htm", ".csv", ".rst")
_LEADING_PREFIX_RE = re.compile(r"^(?:\d{4}[-_]\d{2}[-_]\d{2}[\s_-]*|\d{1,3}[\.\-_、\s]+)")


def _clean_sample_query(raw: str) -> str:
    text = (raw or "").strip().replace("\\", "/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    lower = text.lower()
    for ext in _DOC_EXTENSIONS:
        if lower.endswith(ext):
            text = text[: -len(ext)]
            break
    text = text.replace("_", " ").strip()
    text = _LEADING_PREFIX_RE.sub("", text).strip(" -·#")
    text = re.sub(r"\s+", " ", text)
    if len(text) < 2:
        return ""
    if len(text) > 28:
        text = text[:28].rstrip()
    return text


def _extract_sample_queries(sqlite: KBSQLiteStore, limit: int = 3) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for raw in sqlite.get_sample_titles(limit=max(limit * 3, 8)):
        cleaned = _clean_sample_query(raw)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        queries.append(cleaned)
        if len(queries) >= limit:
            break
    return queries


def _format_size(size_bytes: Any) -> str:
    try:
        num = float(size_bytes)
    except (TypeError, ValueError):
        return ""
    if num <= 0:
        return ""
    if num >= 1024 ** 3:
        return f"{num / (1024 ** 3):.1f} GB"
    if num >= 1024 ** 2:
        return f"{round(num / (1024 ** 2))} MB"
    return f"{round(num / 1024)} KB"


def _effective_api_key_source(saved: dict[str, Any], config: dict[str, Any]) -> tuple[bool, str]:
    """Tell UI whether an embedding key is available without ever revealing the secret."""
    rag_cfg = config.get("rag", {}) or {}
    backend = str(rag_cfg.get("embedding_backend", "auto") or "auto").strip().lower()
    if backend in {"disabled", "none", "local", "ollama"}:
        return False, "none"
    mode = saved.get("mode", "auto") if saved else "auto"
    if mode == "custom" and saved.get("api_key"):
        return True, "saved"
    if rag_cfg.get("embedding_api_key"):
        return True, "provider" if mode in {"provider", "auto", "custom"} else "saved"
    preset = str(rag_cfg.get("embedding_preset") or "").strip().lower()
    key_env = str(rag_cfg.get("embedding_api_key_env") or EMBEDDING_PRESETS.get(preset, {}).get("api_key_env") or "")
    if key_env and os.environ.get(key_env, "").strip():
        return True, "env"
    if preset == "zhipu" and (os.environ.get("ZHIPU_API_KEY", "").strip() or os.environ.get("ZHIPUAI_API_KEY", "").strip()):
        return True, "env"
    return False, "none"


def _effective_dim(config: dict[str, Any], saved: dict[str, Any]) -> int | None:
    rag_cfg = config.get("rag", {}) or {}
    if rag_cfg.get("embedding_dim"):
        return int(rag_cfg["embedding_dim"])
    if saved.get("dim"):
        return int(saved["dim"])
    return None


def _fast_probe_config(config: dict[str, Any]) -> dict[str, Any]:
    rag_cfg = {**(config.get("rag") or {})}
    # Passive settings/status load should never stall >1s if local Ollama isn't running.
    rag_cfg["probe_timeout"] = min(float(rag_cfg.get("probe_timeout", 3) or 3), 0.8)
    rag_cfg["request_timeout"] = min(float(rag_cfg.get("request_timeout", 10) or 10), 2.0)
    return {**config, "rag": rag_cfg}


class RagSettingsService:
    """Inspect, test, configure, backfill, and dry-run search for RAG settings."""

    @staticmethod
    def _presets_payload() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for preset_id, ui in EMBEDDING_PRESET_UI.items():
            defaults = EMBEDDING_PRESETS.get(preset_id, {})
            result.append({
                "id": preset_id,
                "label": ui["label"],
                "badge": ui["badge"],
                "description": ui["description"],
                "base_url": str(defaults.get("base_url") or ""),
                "default_model": str(defaults.get("model") or ""),
                "dim": defaults.get("dim"),
                "api_key_env": str(defaults.get("api_key_env") or ""),
                "suggested_models": list(ui["suggested_models"]),
            })
        return result

    @staticmethod
    def _reusable_providers(config: dict[str, Any]) -> list[dict[str, Any]]:
        providers = AgentService.list_providers(config)["providers"]
        items: list[dict[str, Any]] = []
        for provider in providers:
            preset = str(provider.get("preset") or provider.get("name") or "").strip().lower()
            preset_meta = BUILTIN_PRESETS.get(preset, {})
            emb_preset = EMBEDDING_PRESETS.get(preset, {})
            supports_embedding = provider.get("supports_embedding")
            if supports_embedding is None and "supports_embedding" in preset_meta:
                supports_embedding = preset_meta["supports_embedding"]
            note = str(provider.get("embedding_note") or preset_meta.get("embedding_note") or "")
            raw_models = list(provider.get("models") or [])
            embedding_models: list[dict[str, str]] = []
            seen_ids: set[str] = set()
            for model in raw_models:
                if not isinstance(model, dict):
                    continue
                model_id = str(model.get("id") or "").strip()
                if not model_id or model_id in seen_ids:
                    continue
                kind = str(model.get("kind") or "").strip().lower() or classify_model_kind(model_id)
                if kind == "embedding":
                    seen_ids.add(model_id)
                    embedding_models.append({
                        "id": model_id,
                        "name": str(model.get("name") or model_id),
                        "kind": "embedding",
                    })
            if supports_embedding and emb_preset.get("model"):
                default_emb_id = str(emb_preset["model"])
                if default_emb_id not in seen_ids:
                    embedding_models.append({
                        "id": default_emb_id,
                        "name": default_emb_id,
                        "kind": "embedding",
                    })
            keyless = bool(preset_meta.get("keyless") or preset == "ollama" or preset == "lmstudio" or preset == "vllm")
            items.append({
                "name": provider["name"],
                "preset": preset,
                "configured": bool(provider.get("configured")),
                "keyless": keyless,
                "base_url": str(provider.get("base_url") or ""),
                "supports_embedding": supports_embedding,
                "embedding_note": note,
                "embedding_models": embedding_models,
            })
        return items

    @staticmethod
    def get_summary(config: dict[str, Any], workspace: str | None) -> dict[str, Any]:
        """Lightweight retrieval + embedding readiness summary for UI status cards."""
        saved = get_embedding_config()
        configured_mode = str(saved.get("mode") or "auto")
        rag_cfg = config.get("rag", {}) or {}
        configured_backend = str(rag_cfg.get("embedding_backend", "auto") or "auto").strip().lower()

        vector_stats = {
            "documents": 0,
            "chunks": 0,
            "directory_entries": 0,
            "vector_indexed": 0,
            "vector_pending": 0,
            "vector_error": 0,
        }
        error_samples: list[dict[str, str]] = []
        sample_queries: list[str] = []
        knowledge_ready = False
        stored_signature = None

        if workspace:
            db_path = os.path.join(knowledge_dir(workspace), "knowledge.db")
            if os.path.exists(db_path):
                knowledge_ready = True
                sqlite = KBSQLiteStore(workspace)
                try:
                    vector_stats = sqlite.get_stats()
                    error_samples = [
                        {
                            "title": item["title"],
                            "source": item["source"],
                            "error": redact_secrets(item["error"]),
                        }
                        for item in sqlite.get_vector_error_samples(limit=3)
                    ]
                    sample_queries = _extract_sample_queries(sqlite, limit=3)
                finally:
                    sqlite.close()
                stored_signature = read_signature(workspace)

        probe_cfg = _fast_probe_config(config)
        provider = create_embedding_provider(probe_cfg)
        try:
            model_info = dict(provider.get_model_info())
        except Exception as exc:
            logger.warning("Failed to inspect embedding provider info: %s", exc)
            model_info = {"name": getattr(provider, "name", "unknown"), "model": getattr(provider, "model", ""), "dim": None}

        provider_name = str(model_info.get("name") or getattr(provider, "name", "unknown") or "unknown")
        active_model = str(model_info.get("model") or getattr(provider, "model", "") or "")
        active_dim = model_info.get("dim")

        if configured_mode == "disabled" or configured_backend in {"disabled", "none", "fts_only"}:
            provider_available = False
        else:
            try:
                provider_available = bool(provider.is_available())
            except Exception:
                provider_available = False

        # Re-read model_info after Ollama probe (which populates _dim when running)
        if provider_available and not active_dim:
            try:
                post_info = dict(provider.get_model_info())
                active_dim = post_info.get("dim")
                model_info.update({k: v for k, v in post_info.items() if v is not None})
            except Exception:
                pass

        sig_mismatch = ""
        if workspace and knowledge_ready:
            sig_mismatch = mismatch_reason(workspace, model_info) or ""
            if (
                not sig_mismatch
                and stored_signature
                and int(vector_stats.get("vector_indexed") or 0) > 0
                and active_model
                and stored_signature.get("model")
                and stored_signature.get("model") != active_model
                and provider_name != "unavailable"
            ):
                sig_mismatch = (
                    f"已建索引使用 {stored_signature.get('model')}，"
                    f"当前配置为 {active_model}；需要重建向量索引才能启用语义检索。"
                )

        indexed_docs = int(vector_stats.get("vector_indexed") or 0)
        pending_docs = int(vector_stats.get("vector_pending") or 0)
        error_docs = int(vector_stats.get("vector_error") or 0)
        total_docs = int(vector_stats.get("documents") or 0)

        if configured_mode == "disabled" or configured_backend in {"disabled", "none", "fts_only"}:
            semantic_status = {
                "code": "disabled_by_user",
                "title": "当前仅使用关键词检索",
                "detail": "资料内容不会发送给外部向量接口，精确词和中文 2-gram 检索仍正常可用。",
                "action": "如需搜“意思相近但用词不同”的内容，可在下方选择「云端向量模型」或「本地 Ollama」。",
            }
        elif provider_name == "openai_compat" and not provider_available:
            semantic_status = {
                "code": NOT_CONFIGURED,
                "title": "云端向量模型未就绪（缺少密钥或地址）",
                "detail": "当前选择使用云端向量模型，但还没有可用的 API Key、模型名或地址；目前检索走纯关键词 FTS5。",
                "action": "补充 API Key 或选择已配置的供应商（如硅基流动、百炼、智谱），再测试并保存。",
            }
        elif configured_mode == "auto" and not provider_available and provider_name == "ollama":
            semantic_status = {
                "code": NOT_CONFIGURED,
                "title": "尚未开启向量检索（当前仅关键词）",
                "detail": "还没有启用云端向量模型，本机 Ollama 也未启动，因此检索自动走纯关键词 FTS5 匹配。",
                "action": "在下方选择「云端向量模型」（推荐硅基流动 BGE-M3）或启动本地 Ollama，测试后即可一键补建向量。",
            }
        elif not provider_available and provider_name == "ollama":
            ollama_url = str(rag_cfg.get("ollama_url") or "http://localhost:11434")
            semantic_status = {
                "code": PROVIDER_UNAVAILABLE,
                "title": "本地 Ollama 向量模型未就绪（当前仅关键词）",
                "detail": f"未能从 {ollama_url} 调通模型「{active_model or 'qwen3-embedding:0.6b'}」（服务未启动或未拉取该向量模型）。",
                "action": f"先启动 Ollama 并执行 `ollama pull {active_model or 'qwen3-embedding:0.6b'}`，刷新发现或点击「测试连通性」确认后保存。",
            }
        elif provider_available and (not knowledge_ready or total_docs == 0):
            semantic_status = {
                "code": "no_documents",
                "title": "向量模型已就绪，等待导入资料",
                "detail": "当前向量模型已可用，导入并同步资料后会自动生成向量并启用混合检索。",
                "action": "前往「资料库」导入资料后，可回来运行「召回测试」验证。",
            }
        elif sig_mismatch:
            semantic_status = build_semantic_status(
                available=False,
                provider=provider_name,
                model=active_model,
                dim=active_dim,
                signature_mismatch=sig_mismatch,
                indexed_documents=indexed_docs,
            ).to_dict()
        elif provider_available and knowledge_ready and total_docs > 0 and indexed_docs == 0:
            semantic_status = {
                "code": NO_VECTORS,
                "title": "向量模型已就绪，但资料尚未建向量索引",
                "detail": f"当前资料库共有 {total_docs} 份资料，目前尚未生成向量（0/{total_docs}）；在补建完成前搜索仍只返回关键词匹配结果。",
                "action": "点击上方「为已有资料补建向量」，几秒即可完成整库语义索引。",
            }
        elif provider_available and not sig_mismatch:
            detail = "向量检索与 SQLite FTS5 全文检索已就绪，回答与召回会自动融合语义理解与精确关键词。"
            if knowledge_ready and total_docs > 0 and (pending_docs + error_docs) > 0:
                detail = f"向量模型可用（{indexed_docs}/{total_docs} 份资料已建向量，仍有 {pending_docs + error_docs} 份待补建或上次失败）。"
            semantic_status = {
                "code": OK,
                "title": "混合检索已就绪（向量 + 全文）",
                "detail": detail,
                "action": "可直接在下方「召回测试」输入一个问题验证混合命中效果。" if (pending_docs + error_docs) == 0 else "点击右侧按钮即可为剩余资料补建向量，补齐整库语义召回。",
            }
        else:
            semantic_status = build_semantic_status(
                available=False,
                provider=provider_name,
                model=active_model,
                dim=active_dim,
                indexed_documents=indexed_docs if knowledge_ready else 0,
                vector_error=PROVIDER_UNAVAILABLE if provider_name != "unavailable" else NOT_CONFIGURED,
                provider_reason=str(model_info.get("reason") or ""),
            ).to_dict()

        if not knowledge_ready or total_docs == 0:
            effective_mode = "unavailable"
        elif provider_available and not sig_mismatch and indexed_docs > 0:
            effective_mode = "hybrid"
        else:
            effective_mode = "fts_only"

        needs_rebuild = bool(knowledge_ready and provider_available and sig_mismatch and indexed_docs > 0)
        needs_backfill = bool(
            knowledge_ready
            and provider_available
            and not needs_rebuild
            and (pending_docs + error_docs > 0)
        )

        # User-friendly display provider label
        display_provider = ""
        if saved.get("mode") == "provider" and saved.get("provider_name"):
            display_provider = str(saved["provider_name"])
        elif configured_mode == "disabled" or configured_backend in {"disabled", "none", "fts_only"}:
            display_provider = "disabled"
        elif provider_name == "ollama":
            display_provider = "ollama"
        else:
            display_provider = str(rag_cfg.get("embedding_preset") or model_info.get("base_url") or provider_name)

        return {
            "knowledge_ready": knowledge_ready,
            "effective_mode": effective_mode,
            "configured_mode": configured_mode,
            "embedding_available": provider_available and not sig_mismatch,
            "provider_ready": provider_available,
            "active_provider": provider_name,
            "display_provider": display_provider,
            "active_model": active_model,
            "active_dim": active_dim,
            "stored_signature": stored_signature,
            "signature_mismatch": sig_mismatch,
            "semantic_status": semantic_status,
            "vector_stats": vector_stats,
            "error_samples": error_samples,
            "sample_queries": sample_queries,
            "needs_backfill": needs_backfill,
            "needs_rebuild": needs_rebuild,
        }

    @staticmethod
    def get_settings(config: dict[str, Any], workspace: str | None) -> dict[str, Any]:
        saved = get_embedding_config()
        saved_custom = saved.get("saved_custom") if isinstance(saved.get("saved_custom"), dict) else {}
        rag_cfg = config.get("rag", {}) or {}
        has_key, key_source = _effective_api_key_source(saved, config)
        mode = str(saved.get("mode") or "auto")
        if saved:
            preset = str(saved.get("preset") or rag_cfg.get("embedding_preset") or "siliconflow").strip().lower()
            base_url = str(saved.get("base_url") or "")
            model = str(saved.get("model") or "")
        elif has_key:
            preset = str(rag_cfg.get("embedding_preset") or "siliconflow").strip().lower()
            base_url = str(rag_cfg.get("embedding_base_url") or "")
            model = str(rag_cfg.get("embedding_model") or "")
        else:
            preset = "siliconflow"
            base_url = ""
            model = ""
        if preset in EMBEDDING_PRESETS and not base_url:
            base_url = str(EMBEDDING_PRESETS[preset].get("base_url") or "")
        if preset in EMBEDDING_PRESETS and not model:
            model = str(EMBEDDING_PRESETS[preset].get("model") or "")

        has_saved_custom_key = bool(
            (mode == "custom" and saved.get("api_key"))
            or saved_custom.get("api_key")
        )
        sanitized_cfg = {
            "mode": mode,
            "provider_name": str(saved.get("provider_name") or ""),
            "preset": preset,
            "base_url": base_url,
            "model": model,
            "dim": _effective_dim(config, saved),
            "ollama_url": str(saved.get("ollama_url") or rag_cfg.get("ollama_url") or "http://localhost:11434"),
            "ollama_model": str(saved.get("ollama_model") or rag_cfg.get("ollama_model") or "qwen3-embedding:0.6b"),
            "has_api_key": has_key,
            "api_key_source": key_source,
            "has_saved_custom_key": has_saved_custom_key,
            "saved_custom_preset": str(saved_custom.get("preset") or ""),
            "saved_custom_base_url": str(saved_custom.get("base_url") or ""),
        }
        return {
            "ok": True,
            "config": sanitized_cfg,
            "status": RagSettingsService.get_summary(config, workspace),
            "presets": RagSettingsService._presets_payload(),
            "reusable_providers": RagSettingsService._reusable_providers(config),
        }

    @staticmethod
    def probe_ollama_models(ollama_url: str | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Discover locally installed Ollama models, highlighting embedding-capable ones."""
        saved = get_embedding_config()
        rag_cfg = (config or {}).get("rag", {}) or {}
        raw_url = ollama_url or saved.get("ollama_url") or rag_cfg.get("ollama_url") or "http://localhost:11434"
        clean_url = _strip_v1_suffix(str(raw_url))
        try:
            response = httpx.get(f"{clean_url}/api/tags", timeout=2.0)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return {
                "ok": True,
                "reachable": False,
                "url": clean_url,
                "models": [],
                "embedding_models": [],
                "error": redact_secrets(str(exc)),
            }
        models: list[dict[str, Any]] = []
        seen: set[str] = set()
        raw_list = payload.get("models") if isinstance(payload, dict) else []
        for entry in raw_list if isinstance(raw_list, list) else []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("model") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
            family = str(details.get("family") or "").lower()
            families = [str(f).lower() for f in (details.get("families") or []) if isinstance(f, str)]
            kind = classify_model_kind(name)
            is_embedding = kind == "embedding" or any("bert" in f or "nomic" in f for f in [family, *families])
            models.append({
                "name": name,
                "kind": "embedding" if is_embedding else kind,
                "is_embedding": is_embedding,
                "size_label": _format_size(entry.get("size")),
            })
        models.sort(key=lambda item: (not item["is_embedding"], item["name"]))
        return {
            "ok": True,
            "reachable": True,
            "url": clean_url,
            "models": models,
            "embedding_models": [m["name"] for m in models if m["is_embedding"]],
            "error": "",
        }

    @staticmethod
    def _build_test_provider_with_meta(
        payload: dict[str, Any] | None,
        config: dict[str, Any],
    ) -> tuple[Any, str, bool]:
        """Construct an ephemeral EmbeddingProvider + URL normalization metadata."""
        if not payload:
            base_provider = create_embedding_provider(config)
            if isinstance(base_provider, OpenAICompatibleEmbeddingProvider):
                cleaned, normalized = normalize_openai_base_url(base_provider.base_url)
                return (
                    OpenAICompatibleEmbeddingProvider(
                        base_url=cleaned,
                        model=base_provider.model,
                        api_key=base_provider._api_key,
                        key_env=base_provider.key_env,
                        dim=base_provider._configured_dim,
                        request_timeout=12,
                        max_retries=0,
                    ),
                    cleaned,
                    normalized,
                )
            return base_provider, str(getattr(base_provider, "base_url", "") or ""), False

        mode = str(payload.get("mode") or "auto").strip().lower()
        if mode == "disabled":
            raise ValueError("当前选择了「仅关键词检索」，不会请求向量模型；如需测试请先选择「云端向量模型」或「本地 Ollama」。")

        if mode == "ollama":
            url = _strip_v1_suffix(str(payload.get("ollama_url") or "http://localhost:11434"))
            model = str(payload.get("ollama_model") or "qwen3-embedding:0.6b").strip() or "qwen3-embedding:0.6b"
            return OllamaEmbeddingProvider(base_url=url, model=model, probe_timeout=3, request_timeout=12), url, False

        providers_cfg = (config.get("llm") or {}).get("providers") or {}
        if mode == "provider":
            pname = str(payload.get("provider_name") or "").strip()
            if not pname or pname not in providers_cfg:
                raise ValueError("请先在「AI 与模型」中配置该供应商，再进行测试。")
            pcfg = providers_cfg[pname]
            preset = str(pcfg.get("preset") or "").strip().lower()
            if pname == "ollama" or preset == "ollama":
                url = _strip_v1_suffix(str(pcfg.get("base_url") or ""))
                return (
                    OllamaEmbeddingProvider(
                        base_url=url,
                        model=str(payload.get("model") or "qwen3-embedding:0.6b").strip() or "qwen3-embedding:0.6b",
                        probe_timeout=3,
                        request_timeout=12,
                    ),
                    url,
                    False,
                )
            api_key = resolve_api_key(pcfg)
            if not api_key:
                raise RuntimeError(f"供应商「{pname}」尚未填写 API Key，请先在「AI 与模型」补充密钥。")
            base_url, url_normalized = normalize_openai_base_url(str(pcfg.get("base_url") or ""))
            emb_defaults = EMBEDDING_PRESETS.get(preset, {})
            model = str(payload.get("model") or emb_defaults.get("model") or "").strip()
            if not base_url or not model:
                raise ValueError("请填写或选择该供应商下的向量模型 ID。")
            dim_val = payload.get("dim")
            dim = int(dim_val) if dim_val not in (None, "", 0, "0") else None
            return (
                OpenAICompatibleEmbeddingProvider(
                    base_url=base_url,
                    model=model,
                    api_key=api_key,
                    key_env=str(pcfg.get("api_key_env") or ""),
                    dim=dim,
                    request_timeout=12,
                    max_retries=0,
                ),
                base_url,
                url_normalized,
            )

        if mode == "custom":
            preset = str(payload.get("preset") or "").strip().lower()
            preset_meta = EMBEDDING_PRESETS.get(preset, {})
            raw_url = str(payload.get("base_url") or preset_meta.get("base_url") or "").strip()
            base_url, url_normalized = normalize_openai_base_url(raw_url)
            model = str(payload.get("model") or preset_meta.get("model") or "").strip()
            if not base_url:
                raise ValueError("请填写向量接口根路径（base_url）。")
            if not model:
                raise ValueError("请填写向量模型 ID（如 BAAI/bge-m3）。")
            api_key = str(payload.get("api_key") or "").strip()
            if not api_key:
                saved = get_embedding_config()
                candidates: list[dict[str, Any]] = [saved]
                if isinstance(saved.get("saved_custom"), dict):
                    candidates.append(saved["saved_custom"])
                for cand in candidates:
                    if not cand.get("api_key"):
                        continue
                    prev_raw = str(cand.get("base_url") or EMBEDDING_PRESETS.get(str(cand.get("preset") or ""), {}).get("base_url") or "")
                    prev_url, _ = normalize_openai_base_url(prev_raw)
                    if _same_origin(base_url, prev_url):
                        api_key = str(cand["api_key"])
                        break
            if not api_key:
                api_key = find_matching_provider_key(providers_cfg, base_url, preset=preset)
            if not api_key:
                key_env = str(preset_meta.get("api_key_env") or "")
                if key_env:
                    api_key = os.environ.get(key_env, "").strip()
                if not api_key and preset == "zhipu":
                    api_key = (
                        os.environ.get("ZHIPU_API_KEY", "").strip()
                        or os.environ.get("ZHIPUAI_API_KEY", "").strip()
                    )
            if not api_key:
                raise RuntimeError("请先填写 API Key（若「AI 与模型」已同域名配置，留空会自动复用）。")
            dim_val = payload.get("dim")
            dim = int(dim_val) if dim_val not in (None, "", 0, "0") else None
            return (
                OpenAICompatibleEmbeddingProvider(
                    base_url=base_url,
                    model=model,
                    api_key=api_key,
                    key_env=str(preset_meta.get("api_key_env") or ""),
                    dim=dim,
                    request_timeout=12,
                    max_retries=0,
                ),
                base_url,
                url_normalized,
            )

        # mode == "auto"
        return RagSettingsService._build_test_provider_with_meta(None, config)

    @staticmethod
    def _build_test_provider(payload: dict[str, Any] | None, config: dict[str, Any]):
        """Construct an ephemeral EmbeddingProvider for fast connectivity testing."""
        return RagSettingsService._build_test_provider_with_meta(payload, config)[0]

    @staticmethod
    def test_embedding(payload: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
        """Execute a live 1-string embed probe and return dimension & latency."""
        provider, normalized_base_url, url_normalized = RagSettingsService._build_test_provider_with_meta(payload, config)
        started = time.perf_counter()

        if isinstance(provider, OllamaEmbeddingProvider):
            def _probe_ollama():
                if not provider.client.check_health():
                    raise RuntimeError(
                        f"无法连接本地 Ollama（{provider.base_url}）。请确认 Ollama 已启动。"
                    )
                if provider.client.check_model() is None:
                    raise RuntimeError(
                        f"Ollama 已运行，但未找到向量模型「{provider.model}」（或该模型不支持向量）。"
                        f"请先运行：ollama pull {provider.model}"
                    )
                return provider.embed(["Bobodan 向量连通性测试"])

            fn = _probe_ollama
        else:
            if not provider.is_available():
                raise RuntimeError("当前向量配置不完整（缺少接口地址、模型 ID 或 API Key）。")
            fn = lambda: provider.embed(["Bobodan 向量连通性测试"])

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(fn)
            vectors = future.result(timeout=15)
        except FutureTimeout as exc:
            raise TimeoutError("向量模型请求超时（超过 15 秒），请检查网络或代理设置。") from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            body = redact_secrets(exc.response.text[:240] if exc.response is not None else "")
            if code in {401, 403}:
                raise RuntimeError(f"向量接口鉴权失败（HTTP {code}），请检查 API Key 是否正确或仍有额度。") from exc
            if code == 404:
                raise RuntimeError(
                    "向量接口返回 404：请检查 API 地址是否填到了服务根路径（如 https://api.example.com/v1，不要包含 /embeddings）以及模型 ID 是否拼写正确。"
                ) from exc
            if code == 429:
                raise RuntimeError("向量接口触发限流或额度不足（HTTP 429），请稍后重试或检查账户余额。") from exc
            raise RuntimeError(f"向量接口返回 HTTP {code}：{body or '请检查配置与模型权限。'}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"无法连接向量服务：{redact_secrets(str(exc))}") from exc
        except Exception as exc:
            raise RuntimeError(redact_secrets(str(exc))) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            if isinstance(provider, OpenAICompatibleEmbeddingProvider):
                try:
                    provider._client.close()
                except Exception:
                    pass

        if not vectors or not vectors[0]:
            raise RuntimeError("向量接口有响应，但返回了空向量；请确认填写的是向量模型而不是纯对话模型。")

        latency_ms = round((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "provider": str(getattr(provider, "name", "")),
            "model": str(getattr(provider, "model", "")),
            "dim": len(vectors[0]),
            "latency_ms": latency_ms,
            "normalized_base_url": normalized_base_url,
            "url_normalized": url_normalized,
        }

    @staticmethod
    def _prepare_backfill(
        workspace: str,
        config: dict[str, Any],
        *,
        rebuild: bool = False,
    ) -> tuple[EmbeddingService, dict[str, Any], int, bool, int]:
        db_path = os.path.join(knowledge_dir(workspace), "knowledge.db")
        if not os.path.exists(db_path):
            raise ValueError("当前资料库还没有导入任何资料，无法建立向量索引。")

        embedding = EmbeddingService(config)
        if not embedding.is_available():
            raise RuntimeError("当前向量模型不可用，请先完成配置并确认测试通过。")

        model_info = embedding.get_model_info()
        embedding_dim = model_info.get("dim")
        if not embedding_dim:
            raise RuntimeError("无法获取向量维度（dim），请先执行「测试连通性」或检查接口响应。")
        dim_int = int(embedding_dim)

        sig_mismatch = mismatch_reason(workspace, model_info)
        stored_sig = read_signature(workspace)
        model_changed = bool(
            sig_mismatch
            or (
                stored_sig
                and stored_sig.get("model")
                and model_info.get("model")
                and stored_sig.get("model") != model_info.get("model")
            )
        )
        did_rebuild = bool(rebuild or model_changed)

        sqlite = KBSQLiteStore(workspace)
        try:
            if did_rebuild:
                total = int((sqlite.get_stats() or {}).get("documents") or 0)
            else:
                total = len(sqlite.get_pending_vector_documents())
        finally:
            sqlite.close()
        return embedding, model_info, dim_int, did_rebuild, total

    @staticmethod
    def _execute_backfill(
        workspace: str,
        config: dict[str, Any],
        embedding: EmbeddingService,
        model_info: dict[str, Any],
        dim_int: int,
        did_rebuild: bool,
        *,
        cancel_token: CancelToken | None = None,
        progress=None,
    ) -> dict[str, Any]:
        from obsidian.sync import backfill_vectors as run_backfill

        # Evict cached pipeline and shared Qdrant instance before opening in caller thread.
        clear_retrieval_cache(workspace)
        close_shared_qdrant_store(workspace, config)

        sqlite = KBSQLiteStore(workspace)
        qdrant = shared_qdrant_store(workspace, config)
        try:
            try:
                if did_rebuild:
                    qdrant.delete_collection()
                    qdrant.init_collection(dim_int)
                    sqlite.reset_all_vector_status()
                else:
                    qdrant.init_collection(dim_int)
            except Exception as exc:
                err_kind = classify_vector_error(str(exc))
                if err_kind == VECTOR_STORE_LOCKED:
                    raise RuntimeError("本地向量库正被另一个进程占用，请先关闭其它 Bobodan 实例后重试。") from exc
                raise RuntimeError(redact_secrets(str(exc))) from exc

            backfilled = int(
                run_backfill(
                    sqlite,
                    qdrant,
                    embedding,
                    dim_int,
                    cancel_token=cancel_token,
                    progress=progress,
                )
            )
            stats = sqlite.get_stats()
            if int(stats.get("vector_indexed") or 0) > 0 or did_rebuild:
                write_signature(workspace, model_info)
            error_samples = [
                {
                    "title": item["title"],
                    "source": item["source"],
                    "error": redact_secrets(item["error"]),
                }
                for item in sqlite.get_vector_error_samples(limit=3)
            ]
        finally:
            sqlite.close()
            clear_retrieval_cache(workspace)
            close_shared_qdrant_store(workspace, config)

        return {
            "ok": True,
            "rebuilt": did_rebuild,
            "backfilled": backfilled,
            "dim": dim_int,
            "model": str(model_info.get("model") or ""),
            "vector_stats": stats,
            "error_samples": error_samples,
            "cancelled": bool(cancel_token and cancel_token.is_cancelled()),
        }

    @staticmethod
    def backfill_vectors(
        workspace: str,
        config: dict[str, Any],
        *,
        rebuild: bool = False,
    ) -> dict[str, Any]:
        """Generate vectors for pending docs or rebuild the whole Qdrant collection."""
        embedding, model_info, dim_int, did_rebuild, _ = RagSettingsService._prepare_backfill(
            workspace,
            config,
            rebuild=rebuild,
        )
        return RagSettingsService._execute_backfill(
            workspace,
            config,
            embedding,
            model_info,
            dim_int,
            did_rebuild,
        )

    @staticmethod
    def start_backfill_job(
        workspace: str,
        config: dict[str, Any],
        *,
        rebuild: bool = False,
    ) -> dict[str, Any]:
        """Start (or reuse) a non-blocking background vector backfill job for a workspace."""
        return _BACKFILL_MANAGER.start(workspace, config, rebuild=rebuild)

    @staticmethod
    def get_backfill_job(workspace: str | None) -> dict[str, Any]:
        """Return the latest background vector backfill job snapshot for a workspace."""
        return _BACKFILL_MANAGER.get(workspace)

    @staticmethod
    def cancel_backfill_job(workspace: str | None) -> dict[str, Any]:
        """Cooperatively cancel an active background vector backfill job."""
        return _BACKFILL_MANAGER.cancel(workspace)

    @staticmethod
    def search_test(
        workspace: str,
        config: dict[str, Any],
        query: str,
        top_k: int = 5,
        mode: str = "auto",
    ) -> dict[str, Any]:
        """Run a real retrieval hit-test against the active library."""
        cleaned = (query or "").strip()
        if not cleaned:
            raise ValueError("请输入想测试的检索关键词或问题。")

        started = time.perf_counter()
        raw = KBService(workspace).search(
            query=cleaned,
            top_k=max(1, min(int(top_k), 10)),
            mode=mode or "auto",
            config=config,
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        if not raw.get("ok"):
            raise RuntimeError(str(raw.get("error") or "召回测试执行失败。"))

        hits = []
        for item in raw.get("results") or []:
            meta = item.get("metadata") or {}
            text = str(item.get("text") or "").strip().replace("\r\n", "\n")
            snippet = text[:220] + ("…" if len(text) > 220 else "")
            hits.append({
                "chunk_id": str(item.get("chunk_id") or ""),
                "document_id": str(item.get("document_id") or ""),
                "title": str(item.get("title") or item.get("source") or ""),
                "source": str(item.get("source") or ""),
                "heading_text": str(meta.get("heading_text") or ""),
                "collection": str(item.get("collection") or "material"),
                "score": round(float(item.get("score") or 0.0), 4),
                "retrievers": list(item.get("retrievers") or []),
                "snippet": snippet,
            })

        return {
            "ok": True,
            "query": cleaned,
            "latency_ms": latency_ms,
            "retrieval_mode": str(raw.get("retrieval_mode") or "unavailable"),
            "resolved_mode": str(raw.get("resolved_mode") or ""),
            "semantic_available": bool(raw.get("semantic_available")),
            "semantic_reason": raw.get("semantic_reason"),
            "results": hits,
        }


class RagBackfillManager:
    """Thread-safe background vector backfill coordinator keyed by workspace."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._tokens: dict[str, CancelToken] = {}

    @staticmethod
    def _key(workspace: str | None) -> str:
        return os.path.normcase(os.path.abspath(workspace or "."))

    @staticmethod
    def _idle_snapshot() -> dict[str, Any]:
        return {
            "job_id": "",
            "status": "idle",
            "rebuild": False,
            "done": 0,
            "total": 0,
            "backfilled": 0,
            "current_title": "",
            "dim": None,
            "model": "",
            "error": "",
            "cancelled": False,
            "vector_stats": None,
            "error_samples": [],
        }

    def get(self, workspace: str | None) -> dict[str, Any]:
        key = self._key(workspace)
        with self._lock:
            job = self._jobs.get(key)
            return dict(job) if job else self._idle_snapshot()

    def cancel(self, workspace: str | None) -> dict[str, Any]:
        key = self._key(workspace)
        with self._lock:
            job = self._jobs.get(key)
            token = self._tokens.get(key)
            if not job:
                return self._idle_snapshot()
            if job.get("status") == "running" and token is not None:
                token.cancel()
                job["cancel_requested"] = True
            return dict(job)

    def start(self, workspace: str, config: dict[str, Any], *, rebuild: bool = False) -> dict[str, Any]:
        key = self._key(workspace)
        with self._lock:
            existing = self._jobs.get(key)
            if existing and existing.get("status") == "running":
                return dict(existing)

        embedding, model_info, dim_int, did_rebuild, total = RagSettingsService._prepare_backfill(
            workspace,
            config,
            rebuild=rebuild,
        )
        job_id = f"bf_{uuid.uuid4().hex[:10]}"
        token = CancelToken()
        initial: dict[str, Any] = {
            "job_id": job_id,
            "status": "running",
            "rebuild": did_rebuild,
            "done": 0,
            "total": total,
            "backfilled": 0,
            "current_title": "",
            "dim": dim_int,
            "model": str(model_info.get("model") or ""),
            "error": "",
            "cancelled": False,
            "cancel_requested": False,
            "vector_stats": None,
            "error_samples": [],
            "started_at": time.time(),
            "finished_at": None,
        }
        with self._lock:
            existing = self._jobs.get(key)
            if existing and existing.get("status") == "running":
                return dict(existing)
            self._jobs[key] = initial
            self._tokens[key] = token

        def _on_progress(update: dict[str, Any]) -> None:
            with self._lock:
                job = self._jobs.get(key)
                if not job or job.get("job_id") != job_id:
                    return
                job["done"] = int(update.get("done") or 0)
                job["total"] = int(update.get("total") or job["total"])
                job["backfilled"] = int(update.get("backfilled") or 0)
                job["current_title"] = str(update.get("current_title") or "")

        def _worker() -> None:
            try:
                result = RagSettingsService._execute_backfill(
                    workspace,
                    config,
                    embedding,
                    model_info,
                    dim_int,
                    did_rebuild,
                    cancel_token=token,
                    progress=_on_progress,
                )
                with self._lock:
                    job = self._jobs.get(key)
                    if not job or job.get("job_id") != job_id:
                        return
                    cancelled = bool(result.get("cancelled"))
                    job["status"] = "cancelled" if cancelled else "completed"
                    job["cancelled"] = cancelled
                    job["backfilled"] = int(result.get("backfilled") or 0)
                    if not cancelled:
                        job["done"] = int(job["total"])
                    job["current_title"] = ""
                    job["vector_stats"] = result.get("vector_stats")
                    job["error_samples"] = result.get("error_samples") or []
                    job["finished_at"] = time.time()
            except Exception as exc:
                with self._lock:
                    job = self._jobs.get(key)
                    if not job or job.get("job_id") != job_id:
                        return
                    job["status"] = "failed"
                    job["error"] = redact_secrets(str(exc))
                    job["current_title"] = ""
                    job["finished_at"] = time.time()

        thread = threading.Thread(target=_worker, name=f"rag-backfill-{job_id}", daemon=True)
        thread.start()
        return dict(initial)


_BACKFILL_MANAGER = RagBackfillManager()
