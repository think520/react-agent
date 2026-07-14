from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import httpx


SEARCH_TIMEOUT = 20.0
EXA_MCP_URL = "https://mcp.exa.ai/mcp"


@dataclass
class SearchCandidate:
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None
    rank: int = 0
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SearchProviderError(RuntimeError):
    def __init__(self, message: str, kind: str = "network"):
        super().__init__(message)
        self.kind = kind


class SearchProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def search(self, query: str, max_results: int = 6) -> list[SearchCandidate]: ...


def _error_kind(exc: Exception) -> str:
    message = str(exc).lower()
    if any(token in message for token in ("401", "403", "unauthorized", "api key")):
        return "authentication"
    if any(token in message for token in ("402", "429", "quota", "rate limit")):
        return "rate_limited"
    if "timeout" in message:
        return "timeout"
    return "network"


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None):
        self.api_key = (api_key or os.getenv("TAVILY_API_KEY") or "").strip()
        self.transport = transport

    def available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 6) -> list[SearchCandidate]:
        if not self.available():
            raise SearchProviderError("Tavily is not configured", "not_configured")
        try:
            with httpx.Client(timeout=SEARCH_TIMEOUT, transport=self.transport) as client:
                response = client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"query": query, "max_results": max_results, "search_depth": "basic"},
                )
            if response.status_code in {401, 403}:
                raise SearchProviderError("Tavily authentication failed", "authentication")
            if response.status_code in {402, 429}:
                raise SearchProviderError("Tavily rate limit reached", "rate_limited")
            response.raise_for_status()
            payload = response.json()
        except SearchProviderError:
            raise
        except Exception as exc:
            raise SearchProviderError(f"Tavily search failed: {exc}", _error_kind(exc)) from exc
        return [
            SearchCandidate(
                title=str(item.get("title") or "Untitled source"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or ""),
                published_at=item.get("published_date"),
                rank=index,
                provider=self.name,
            )
            for index, item in enumerate(payload.get("results") or [], 1)
            if item.get("url")
        ][:max_results]


def _json_payload(text: str) -> Any:
    value = text.strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"(?:\[|\{)[\s\S]*(?:\]|\})", value)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _candidate_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("results", "data", "items"):
        rows = _candidate_rows(value.get(key))
        if rows:
            return rows
    return []


def _exa_text_rows(text: str) -> list[dict[str, Any]]:
    rows = []
    for block in re.split(r"\n\s*---\s*\n", text.strip()):
        title = re.search(r"^Title:\s*(.+)$", block, flags=re.MULTILINE)
        url = re.search(r"^URL:\s*(https?://\S+)$", block, flags=re.MULTILINE)
        published = re.search(r"^Published:\s*(.+)$", block, flags=re.MULTILINE)
        if not title or not url:
            continue
        highlight = block.split("Highlights:", 1)[1].strip() if "Highlights:" in block else ""
        rows.append({
            "title": title.group(1).strip(),
            "url": url.group(1).strip(),
            "text": highlight,
            "published_at": published.group(1).strip() if published else None,
        })
    return rows


class ExaSearchProvider:
    name = "exa"

    def __init__(self, manager_factory=None):
        self.manager_factory = manager_factory

    def available(self) -> bool:
        return True

    def _manager(self):
        if self.manager_factory:
            return self.manager_factory()
        from mcp_client.config import MCPConfig, MCPServerConfig
        from mcp_client.manager import MCPManager

        config = MCPConfig(
            enabled=True,
            connection_timeout=10,
            tool_call_timeout=SEARCH_TIMEOUT,
            servers={
                "exa": MCPServerConfig(
                    name="exa",
                    enabled=True,
                    transport="streamable_http",
                    url=EXA_MCP_URL,
                    connection_timeout=10,
                )
            },
        )
        return MCPManager(config)

    def search(self, query: str, max_results: int = 6) -> list[SearchCandidate]:
        manager = None
        try:
            manager = self._manager()
            result = manager.call("exa", "web_search_exa", {"query": query, "numResults": max_results})
        except Exception as exc:
            raise SearchProviderError(f"Exa search failed: {exc}", _error_kind(exc)) from exc
        finally:
            shutdown = getattr(manager, "shutdown", None)
            if callable(shutdown):
                shutdown()
        if result.get("isError"):
            message = " ".join(str(item.get("text") or "") for item in result.get("content") or [])
            raise SearchProviderError(message or "Exa search failed", _error_kind(RuntimeError(message)))
        texts = [str(item.get("text") or "") for item in result.get("content") or [] if item.get("type") == "text"]
        payload = next((parsed for text in texts if (parsed := _json_payload(text)) is not None), None)
        rows = _candidate_rows(payload)
        if not rows:
            rows = [row for text in texts for row in _exa_text_rows(text)]
        if not rows:
            return []
        return [
            SearchCandidate(
                title=str(item.get("title") or "Untitled source"),
                url=str(item.get("url") or item.get("id") or ""),
                snippet=str(item.get("text") or item.get("content") or item.get("snippet") or ""),
                published_at=item.get("publishedDate") or item.get("published_at"),
                rank=index,
                provider=self.name,
            )
            for index, item in enumerate(rows, 1)
            if item.get("url") or str(item.get("id") or "").startswith("http")
        ][:max_results]


class AutoSearchProvider:
    name = "auto"

    def __init__(self, providers: list[SearchProvider]):
        self.providers = providers
        self.attempts: list[dict[str, Any]] = []

    def available(self) -> bool:
        return any(provider.available() for provider in self.providers)

    def search(self, query: str, max_results: int = 6) -> list[SearchCandidate]:
        self.attempts = []
        for provider in self.providers:
            if not provider.available():
                self.attempts.append({"provider": provider.name, "status": "not_configured"})
                continue
            try:
                results = provider.search(query, max_results)
                self.attempts.append({"provider": provider.name, "status": "ok" if results else "empty"})
                if results:
                    return results
            except SearchProviderError as exc:
                self.attempts.append({"provider": provider.name, "status": "error", "error_kind": exc.kind})
        return []
