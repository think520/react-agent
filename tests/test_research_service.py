from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from research.providers import AutoSearchProvider, ExaSearchProvider, SearchCandidate, SearchProviderError, TavilySearchProvider
from research.reader import UnsafeURLError, canonical_url, fetch_page, validate_public_url
from service.research_service import ResearchService


class FakeProvider:
    def __init__(self, name, results=None, error=None, available=True):
        self.name = name
        self.results = results or []
        self.error = error
        self._available = available
        self.calls = 0

    def available(self):
        return self._available

    def search(self, query, max_results=6):
        self.calls += 1
        if self.error:
            raise self.error
        return self.results[:max_results]


def test_auto_provider_uses_ordered_fallback():
    first = FakeProvider("tavily", error=SearchProviderError("limited", "rate_limited"))
    second = FakeProvider("exa", [SearchCandidate("Docs", "https://example.com/docs", provider="exa")])
    provider = AutoSearchProvider([first, second])

    results = provider.search("topic")

    assert results[0].provider == "exa"
    assert first.calls == second.calls == 1
    assert provider.attempts == [
        {"provider": "tavily", "status": "error", "error_kind": "rate_limited"},
        {"provider": "exa", "status": "ok"},
    ]


def test_tavily_classifies_authentication_failure():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "bad key"}))
    provider = TavilySearchProvider("secret", transport=transport)

    with pytest.raises(SearchProviderError) as exc:
        provider.search("topic")

    assert exc.value.kind == "authentication"


def test_exa_parses_mcp_text_results():
    class Manager:
        def call(self, server, tool, args):
            return {"isError": False, "content": [{"type": "text", "text": "Title: Guide\nURL: https://example.com/guide\nPublished: 2026-07-14\nHighlights:\nUseful result"}]}

        def shutdown(self):
            pass

    results = ExaSearchProvider(manager_factory=Manager).search("topic", 1)
    assert results[0].title == "Guide"
    assert results[0].snippet == "Useful result"


def test_url_validation_rejects_private_dns(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 0))])
    with pytest.raises(UnsafeURLError):
        validate_public_url("https://example.com/private")


def test_direct_reader_extracts_text_and_blocks_oversized_content():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html><title>Lesson</title><article><h1>Topic</h1><p>Useful evidence.</p></article></html>")

    result = fetch_page(
        "https://example.com/lesson",
        transport=httpx.MockTransport(handler),
        resolver=canonical_url,
    )

    assert result.reader == "direct"
    assert result.title == "Lesson"
    assert "Useful evidence" in result.content


def test_reader_uses_jina_only_after_direct_failure():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.host == "example.com":
            return httpx.Response(403, text="blocked")
        return httpx.Response(200, text="Title: Readable page\n\nEvidence from Jina.")

    result = fetch_page(
        "https://example.com/article",
        transport=httpx.MockTransport(handler),
        resolver=canonical_url,
    )

    assert result.reader == "jina"
    assert result.title == "Readable page"
    assert calls == ["https://example.com/article", "https://r.jina.ai/https://example.com/article"]


def test_research_store_keeps_immutable_deduplicated_snapshots(tmp_path):
    provider = FakeProvider("exa", [SearchCandidate("One", "https://example.com/a", "summary", provider="exa")])
    snapshot = SimpleNamespace(
        final_url="https://example.com/a", title="One", domain="example.com",
        content="Evidence paragraph.", content_hash="same-hash", reader="direct",
    )
    service = ResearchService(str(tmp_path), providers={"tavily": provider, "exa": provider}, page_fetcher=lambda *args, **kwargs: snapshot)
    search = service.search("session-1", "topic", "exa")

    first = service.select(search["search_id"], "session-1", [search["candidates"][0]["candidate_id"]])
    second = service.select(search["search_id"], "session-1", [search["candidates"][0]["candidate_id"]])

    assert first["sources"][0]["snapshot_id"] == second["sources"][0]["snapshot_id"]
    evidence = service.evidence(first["research_id"], "session-1")
    assert evidence["sources"][0]["reader"] == "direct"
    assert "Evidence paragraph" in evidence["content"]


def test_direct_url_becomes_candidate_without_search_provider(tmp_path):
    unavailable = FakeProvider("exa", available=False)
    service = ResearchService(str(tmp_path), providers={"tavily": unavailable, "exa": unavailable})

    result = service.search("session-1", "https://Example.com/article#part", "auto")

    assert result["provider"] == "direct"
    assert result["candidates"][0]["url"] == "https://example.com/article"
    assert unavailable.calls == 0


def test_research_is_scoped_to_its_session(tmp_path):
    provider = FakeProvider("exa", [SearchCandidate("One", "https://example.com/a", provider="exa")])
    service = ResearchService(str(tmp_path), providers={"tavily": provider, "exa": provider})
    search = service.search("session-1", "topic", "exa")

    with pytest.raises(FileNotFoundError):
        service.select(search["search_id"], "session-2", [search["candidates"][0]["candidate_id"]])
