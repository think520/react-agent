"""Embedding provider registry (rag_design B2).

Until this module existed, `EmbeddingService` could only talk to a local Ollama
instance, so a machine without Ollama running could not build vectors at all -
which is exactly the state the product was found in (70/70 documents pending).

The locked decision (调研报告 ch10 / `rag_design` §11) is: do not bundle an ONNX
model, keep Ollama as the offline option, and let a user-configured
OpenAI-compatible API be the normal path, with SiliconFlow bge-m3 as the
recommended free tier.

Downstream code (Qdrant collection init, hybrid retriever, sync backfill) needs
only three things from a provider: `is_available()`, `embed(texts)`,
`get_model_info()`. That is the whole contract.

Secrets: a key never belongs in `config.yaml` (it is tracked), in a log line or
in an error message. It travels in an Authorization header and nowhere else.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_BATCH_SIZE = 32

# Presets: base URL + default model + the env var that should hold the key.
# Model ids match what the research report recommended; every field can be
# overridden by the rag.* keys below.
PRESETS: dict[str, dict[str, Any]] = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-m3",
        "api_key_env": "SILICONFLOW_API_KEY",
        "dim": 1024,
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "text-embedding-v4",
        "api_key_env": "DASHSCOPE_API_KEY",
        "dim": 1024,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "text-embedding-3-small",
        "api_key_env": "OPENAI_API_KEY",
        "dim": 1536,
    },
    # 智谱 v4 是 OpenAI 兼容接口（实测 2026-09-23：embedding-3 默认 2048 维，
    # 0.5 元/百万 tokens）。该模型也支持 dimensions=1024，但 provider 目前不发这个
    # 参数，所以这里必须写 API 的默认维度，否则 Qdrant collection 会按错维度建。
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "embedding-3",
        "api_key_env": "ZHIPU_API_KEY",
        "dim": 2048,
    },
    "ollama": {
        "base_url": "http://localhost:11434",
        "model": "qwen3-embedding:0.6b",
        "api_key_env": "",
        "dim": None,
    },
}


class EmbeddingProvider(Protocol):
    """What the rest of RAG is allowed to depend on."""

    name: str
    model: str

    def is_available(self, force_refresh: bool = False) -> bool: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def get_model_info(self) -> dict: ...


class UnavailableEmbeddingProvider:
    """No provider: retrieval stays FTS5-only instead of silently degrading."""

    name = "unavailable"
    model = ""

    def __init__(self, reason: str = "") -> None:
        self.reason = reason

    def is_available(self, force_refresh: bool = False) -> bool:
        return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError(self.reason or "no embedding provider is configured")

    def get_model_info(self) -> dict:
        return {"name": self.name, "model": "", "dim": None, "reason": self.reason}


class OllamaEmbeddingProvider:
    """Adapter around the pre-existing Ollama client (kept, not rewritten)."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        probe_timeout: float = 3,
        request_timeout: float = 10,
    ) -> None:
        from rag.ollama import OllamaEmbeddingClient

        self.model = model
        self.base_url = base_url
        self.client = OllamaEmbeddingClient(
            base_url=base_url,
            model=model,
            probe_timeout=probe_timeout,
            request_timeout=request_timeout,
        )

    def is_available(self, force_refresh: bool = False) -> bool:
        try:
            return bool(self.client.is_available(force_refresh=force_refresh))
        except Exception:
            return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.client.embed(texts)

    def get_model_info(self) -> dict:
        try:
            info = dict(self.client.get_model_info())
        except Exception:
            info = {}
        info.setdefault("name", self.name)
        info.setdefault("model", self.model)
        info.setdefault("dim", None)
        return info


class OpenAICompatibleEmbeddingProvider:
    """`POST {base_url}/embeddings` — the shape every major vendor now speaks."""

    name = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        key_env: str = "",
        dim: int | None = None,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        batch_size: int = DEFAULT_BATCH_SIZE,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self._api_key = api_key or ""
        self.key_env = key_env
        self._configured_dim = int(dim) if dim else None
        self._observed_dim: int | None = None
        self.request_timeout = request_timeout
        self.batch_size = max(1, int(batch_size))
        self._client = client or httpx.Client(timeout=request_timeout)

    @property
    def dim(self) -> int | None:
        return self._configured_dim or self._observed_dim

    def is_available(self, force_refresh: bool = False) -> bool:
        """Configuration check only - no request.

        A network probe on every call would be worse than useless: the real
        probe is the first embed, and failures there already degrade to `None`
        one layer up (`EmbeddingService.embed_texts`).
        """
        return bool(self.base_url and self.model and self._api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.is_available():
            raise RuntimeError("embedding provider is not configured")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self.batch_size]))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.post(
            self.base_url + "/embeddings",
            headers={"Authorization": "Bearer " + self._api_key},
            json={"model": self.model, "input": texts},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") or []
        # Providers are allowed to return rows out of order; index is the truth.
        rows = sorted(rows, key=lambda row: row.get("index", 0))
        vectors = [row.get("embedding") or [] for row in rows]
        if len(vectors) != len(texts):
            raise RuntimeError(
                "embedding provider returned " + str(len(vectors))
                + " vectors for " + str(len(texts)) + " inputs"
            )
        if vectors and vectors[0]:
            self._observed_dim = len(vectors[0])
        return vectors

    def resolve_dim(self) -> int | None:
        """Dimension for the Qdrant collection.

        Config wins; otherwise the dimension observed on the last embed; failing
        that, one tiny probe request - because a collection that is never
        created means vectors are silently never written (the P1-18 trap).
        """
        if self.dim:
            return self.dim
        if not self.is_available():
            return None
        self.embed(["dimension probe"])
        return self.dim

    def get_model_info(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "dim": self.dim,
            "base_url": self.base_url,
            "key_env": self.key_env,
            "key_present": bool(self._api_key),
        }


def _api_settings(rag_cfg: dict) -> dict:
    preset_name = str(rag_cfg.get("embedding_preset") or "").strip().lower()
    preset = PRESETS.get(preset_name, {})
    base_url = str(rag_cfg.get("embedding_base_url") or preset.get("base_url") or "").strip()
    model = str(rag_cfg.get("embedding_model") or preset.get("model") or "").strip()
    key_env = str(rag_cfg.get("embedding_api_key_env") or preset.get("api_key_env") or "").strip()
    api_key = os.environ.get(key_env, "").strip() if key_env else ""
    if not api_key:
        # Discouraged escape hatch for a local, untracked override.
        api_key = str(rag_cfg.get("embedding_api_key") or "").strip()
    dim = rag_cfg.get("embedding_dim") or preset.get("dim")
    return {
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "key_env": key_env,
        "dim": dim,
        "configured": bool(base_url and model and api_key),
    }


def _ollama_provider(rag_cfg: dict) -> OllamaEmbeddingProvider:
    return OllamaEmbeddingProvider(
        base_url=rag_cfg.get("ollama_url", "http://localhost:11434"),
        model=rag_cfg.get("ollama_model", "qwen3-embedding:0.6b"),
        probe_timeout=rag_cfg.get("probe_timeout", 3),
        request_timeout=rag_cfg.get("request_timeout", 10),
    )


def _api_provider(rag_cfg: dict, api: dict) -> OpenAICompatibleEmbeddingProvider:
    return OpenAICompatibleEmbeddingProvider(
        base_url=api["base_url"],
        model=api["model"],
        api_key=api["api_key"],
        key_env=api["key_env"],
        dim=api["dim"],
        request_timeout=rag_cfg.get("embedding_timeout", DEFAULT_REQUEST_TIMEOUT),
        batch_size=rag_cfg.get("embedding_batch_size", DEFAULT_BATCH_SIZE),
    )


def create_embedding_provider(config: dict | None = None) -> EmbeddingProvider:
    """Pick a provider from config.

    - `ollama`: force the local Ollama path.
    - `openai_compat` (aliases: `openai`, `api`): force the API path; if it is
      under-configured it stays unavailable and retrieval degrades to FTS5
      rather than quietly using something else.
    - `local`: no provider - this product does not bundle a local model.
    - `auto` (default): a fully configured API provider wins, otherwise Ollama.
    """
    rag_cfg = (config or {}).get("rag", {}) or {}
    backend = str(rag_cfg.get("embedding_backend", "auto") or "auto").strip().lower()
    api = _api_settings(rag_cfg)
    if backend == "ollama":
        return _ollama_provider(rag_cfg)
    if backend in {"openai", "openai_compat", "api"}:
        return _api_provider(rag_cfg, api)
    if backend == "local":
        return UnavailableEmbeddingProvider(
            "local embeddings are not bundled by design (rag_design ch10 decision)"
        )
    if api["configured"]:
        return _api_provider(rag_cfg, api)
    return _ollama_provider(rag_cfg)
