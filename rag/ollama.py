"""Ollama embedding client — probe, embed, cache availability."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3-embedding:0.6b"
DEFAULT_PROBE_TIMEOUT = 3
DEFAULT_REQUEST_TIMEOUT = 10


class OllamaEmbeddingClient:
    """Client for Ollama's embedding API with cached availability probing."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        probe_timeout: int = DEFAULT_PROBE_TIMEOUT,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.probe_timeout = probe_timeout
        self.request_timeout = request_timeout
        self._available: bool | None = None  # None = not probed yet
        self._model_info: dict[str, Any] | None = None
        self._dim: int | None = None

    def check_health(self) -> bool:
        """Check if Ollama service is reachable (GET /api/tags)."""
        try:
            resp = httpx.get(
                f"{self.base_url}/api/tags",
                timeout=self.probe_timeout,
            )
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            return False

    def check_model(self) -> dict | None:
        """Check model capabilities via POST /api/show. Returns info dict or None."""
        try:
            resp = httpx.post(
                f"{self.base_url}/api/show",
                json={"name": self.model},
                timeout=self.probe_timeout,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            capabilities = data.get("capabilities") or []
            if "embedding" not in capabilities:
                logger.warning("Ollama model %s does not have embedding capability", self.model)
                return None
            return data
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            return None

    def is_available(self, force_refresh: bool = False) -> bool:
        """Check if Ollama embedding is available. Cached after first probe.

        Final check is a real embed() request — capabilities hint is not enough.
        """
        if self._available is not None and not force_refresh:
            return self._available

        # Layer 1: service reachable
        if not self.check_health():
            self._available = False
            return False

        # Layer 2: model exists and has embedding capability
        model_data = self.check_model()
        if model_data is None:
            self._available = False
            return False

        # Cache model info from show
        model_details = model_data.get("details") or {}
        param_size = model_details.get("parameter_size", "")
        self._model_info = {
            "model": self.model,
            "parameter_size": param_size,
            "backend": "ollama",
        }

        # Try to get dim from model info
        model_meta = model_data.get("model_info") or {}
        for key, val in model_meta.items():
            if "embedding_length" in key:
                self._dim = int(val)
                break

        # Layer 3: real embedding request
        try:
            vectors = self.embed(["test"])
            if vectors and vectors[0]:
                self._dim = len(vectors[0])
                self._available = True
                logger.info(
                    "Ollama embedding available: model=%s dim=%d",
                    self.model,
                    self._dim,
                )
                return True
        except Exception:
            pass

        self._available = False
        return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts. POST /api/embed.

        Raises httpx.HTTPError on connection/timeout issues.
        """
        resp = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=self.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("embeddings") or []

    def get_model_info(self) -> dict:
        """Return model metadata: {model, dim, backend}."""
        info = {
            "model": self.model,
            "dim": self._dim,
            "backend": "ollama",
        }
        if self._model_info:
            info.update(
                {k: v for k, v in self._model_info.items() if k not in info}
            )
        return info

    def refresh(self, force: bool = False) -> bool:
        """Manually refresh availability cache. Returns is_available()."""
        return self.is_available(force_refresh=force)
