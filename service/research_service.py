from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit

from research.providers import AutoSearchProvider, ExaSearchProvider, SearchProviderError, TavilySearchProvider
from research.reader import canonical_url, evidence_excerpt, fetch_page
from research.store import ResearchStore


_QUALITY_ORDER = {"official": 0, "reference": 1, "unknown": 2, "community": 3}


def _quality_hint(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith((".gov", ".gov.cn", ".edu", ".edu.cn")):
        return "official"
    if any(token in host for token in ("docs.", "developer.", "support.", "wikipedia.org")):
        return "reference"
    if any(token in host for token in ("reddit.com", "zhihu.com", "stackoverflow.com", "medium.com")):
        return "community"
    return "unknown"


class ResearchService:
    def __init__(self, workspace: str, providers: dict | None = None, page_fetcher=fetch_page):
        self.workspace = workspace
        self._store = None
        self.providers = providers or {
            "tavily": TavilySearchProvider(),
            "exa": ExaSearchProvider(),
        }
        self.page_fetcher = page_fetcher

    @property
    def store(self) -> ResearchStore:
        if self._store is None:
            self._store = ResearchStore(self.workspace)
        return self._store

    def _provider(self, name: str):
        if name == "auto":
            return AutoSearchProvider([self.providers["tavily"], self.providers["exa"]])
        if name not in self.providers:
            raise ValueError("Unknown search provider")
        return self.providers[name]

    def search(self, session_id: str, query: str, provider_name: str = "auto") -> dict:
        query = query.strip()
        try:
            direct_url = canonical_url(query)
        except ValueError:
            direct_url = ""
        if direct_url:
            search_id = self.store.create_search(session_id, query, "direct", {"attempts": []})
            candidate = self.store.add_candidates(search_id, [{
                "title": urlsplit(direct_url).hostname or direct_url,
                "url": direct_url,
                "canonical_url": direct_url,
                "domain": urlsplit(direct_url).hostname or "",
                "snippet": "用户提供的网页地址，确认后读取正文。",
                "published_at": None,
                "rank": 1,
                "provider": "direct",
                "quality_hint": _quality_hint(direct_url),
            }])
            return {"search_id": search_id, "query": query, "provider": "direct", "candidates": candidate, "diagnostics": {"attempts": []}}
        provider = self._provider(provider_name)
        if not provider.available():
            raise SearchProviderError("The selected search provider is not available", "not_configured")
        results = provider.search(query, 6)
        diagnostics = {"attempts": getattr(provider, "attempts", [])}
        used_provider = results[0].provider if results else provider_name
        search_id = self.store.create_search(session_id, query, used_provider, diagnostics)
        candidates = []
        seen = set()
        for result in results:
            try:
                normalized = canonical_url(result.url)
            except ValueError:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append({
                **result.to_dict(),
                "canonical_url": normalized,
                "domain": urlsplit(normalized).hostname or "",
                "quality_hint": _quality_hint(normalized),
            })
        rows = self.store.add_candidates(search_id, candidates[:6])
        return {"search_id": search_id, "query": query, "provider": used_provider, "candidates": rows, "diagnostics": diagnostics}

    def select(self, search_id: str, session_id: str, candidate_ids: list[str], jina_fallback: bool = True) -> dict:
        search = self.store.get_search(search_id)
        if not search or search["session_id"] != session_id:
            raise FileNotFoundError("Web search not found")
        selected = [item for item in search["candidates"] if item["id"] in set(candidate_ids)]
        if not 1 <= len(selected) <= 4 or len(candidate_ids) != len(set(candidate_ids)) or len(selected) != len(candidate_ids):
            raise ValueError("Select between one and four valid sources")
        research_id = self.store.create_research(search_id, session_id)
        sources = []
        failed = []
        fetched = {}
        with ThreadPoolExecutor(max_workers=len(selected)) as executor:
            futures = {
                executor.submit(self.page_fetcher, candidate["url"], jina_fallback=jina_fallback): candidate
                for candidate in selected
            }
            for future in as_completed(futures):
                candidate = futures[future]
                try:
                    fetched[candidate["id"]] = (future.result(), None)
                except Exception as exc:
                    fetched[candidate["id"]] = (None, exc)
        for candidate in selected:
            snapshot, fetch_error = fetched[candidate["id"]]
            try:
                if fetch_error:
                    raise fetch_error
                excerpt = evidence_excerpt(snapshot.content, search["query"])
                snapshot_id = self.store.save_snapshot(candidate["canonical_url"], snapshot, excerpt)
                self.store.add_research_source(research_id, candidate["id"], "ready", snapshot_id=snapshot_id)
                sources.append({
                    "source_type": "web",
                    "source_id": snapshot_id,
                    "snapshot_id": snapshot_id,
                    "title": snapshot.title or candidate["title"],
                    "url": snapshot.final_url,
                    "domain": snapshot.domain,
                    "accessed_at": self.store.get_snapshot(snapshot_id)["accessed_at"],
                    "reader": snapshot.reader,
                })
            except Exception as exc:
                self.store.add_research_source(research_id, candidate["id"], "failed", error=str(exc))
                failed.append(candidate["id"])
        status = "ready" if sources and not failed else "partial" if sources else "failed"
        self.store.finish_research(research_id, status)
        return {"research_id": research_id, "status": status, "sources": sources, "failed_source_ids": failed}

    def auto_research(
        self,
        session_id: str,
        query: str,
        provider_name: str = "auto",
        jina_fallback: bool = True,
        max_sources: int = 3,
    ) -> dict:
        search = self.search(session_id, query, provider_name)
        ordered = sorted(
            search["candidates"],
            key=lambda item: (_QUALITY_ORDER.get(item.get("quality_hint"), 9), int(item.get("rank") or 0)),
        )
        selected = []
        domains = set()
        for candidate in ordered:
            domain = str(candidate.get("domain") or "").casefold()
            if domain and domain in domains:
                continue
            selected.append(candidate)
            if domain:
                domains.add(domain)
            if len(selected) >= max(1, min(max_sources, 3)):
                break
        if not selected:
            raise SearchProviderError("The search provider returned no usable sources", "empty")
        result = self.select(
            search["search_id"],
            session_id,
            [item["candidate_id"] for item in selected],
            jina_fallback=jina_fallback,
        )
        evidence = self.evidence(result["research_id"], session_id) if result["sources"] else {
            "content": "",
            "sources": [],
        }
        return {
            **result,
            "search_id": search["search_id"],
            "query": search["query"],
            "provider": search["provider"],
            "candidates": search["candidates"],
            "selected_candidate_ids": [item["candidate_id"] for item in selected],
            "content": evidence["content"],
        }

    def evidence(self, research_id: str, session_id: str | None = None, max_chars: int = 18_000) -> dict:
        research = self.store.get_research(research_id)
        if not research or (session_id and research["session_id"] != session_id):
            raise FileNotFoundError("Web research not found")
        sources = []
        blocks = []
        remaining = max_chars
        for row in research["sources"]:
            if row["status"] != "ready" or not row["snapshot_id"]:
                continue
            excerpt = (row["excerpt"] or "")[: min(6000, remaining)]
            if not excerpt:
                continue
            sources.append({
                "source_type": "web", "source_id": row["snapshot_id"], "snapshot_id": row["snapshot_id"],
                "title": row["title"], "url": row["final_url"], "domain": row["domain"],
                "accessed_at": row["accessed_at"], "reader": row["reader"],
            })
            blocks.append(f"[Web source {len(sources)}: {row['title']}]\nURL: {row['final_url']}\nAccessed: {row['accessed_at']}\n{excerpt}")
            remaining -= len(excerpt)
            if remaining <= 0:
                break
        return {"research": research, "sources": sources, "content": "\n\n".join(blocks)}

    def source(self, snapshot_id: str) -> dict:
        source = self.store.get_snapshot(snapshot_id)
        if not source:
            raise FileNotFoundError("Web source not found")
        return {key: source[key] for key in ("id", "final_url", "title", "domain", "excerpt", "accessed_at", "reader")}

    def status(self, provider_name: str) -> dict:
        provider = self._provider(provider_name)
        return {"provider": provider_name, "available": provider.available()}

    def test(self, provider_name: str) -> dict:
        provider = self._provider(provider_name)
        results = provider.search("Bobodan learning assistant", 1)
        if not results:
            raise SearchProviderError("The search provider returned no results", "empty")
        return {"provider": provider_name, "available": True, "result_count": len(results)}
