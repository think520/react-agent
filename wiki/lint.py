"""Wiki health checker — finds orphans, broken links, missing pages, stale pages."""

import json
import os
import time
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import yaml

from .schema import WikiConfig

logger = logging.getLogger(__name__)

WIKILINK_RE = re.compile(r'\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]')
SEMANTIC_PROMPT = """Review these Wiki page excerpts. Return JSON only:
{{"issues":[{{"type":"contradiction|stale|missing-knowledge","pages":["title"],"reason":"short explanation"}}]}}

Do not edit pages. Report only high-confidence review candidates grounded in the supplied excerpts.

{pages}
"""


@dataclass
class LintResult:
    """Result of a wiki health check."""
    total_pages: int = 0
    orphan_pages: list[str] = field(default_factory=list)       # 无入链
    broken_links: list[dict] = field(default_factory=list)      # 指向不存在页面
    missing_pages: list[str] = field(default_factory=list)      # 被引用但不存在
    stale_pages: list[str] = field(default_factory=list)        # 超过 N 天未更新
    index_mismatches: list[str] = field(default_factory=list)
    duplicate_candidates: list[dict] = field(default_factory=list)
    contradiction_candidates: list[str] = field(default_factory=list)
    semantic_candidates: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return (
            not self.orphan_pages and not self.broken_links
            and not self.missing_pages and not self.index_mismatches
            and not self.duplicate_candidates
        )


class WikiLinter:
    """Checks wiki health: orphans, broken links, missing pages, staleness."""

    def __init__(self, vault_path: str, config: WikiConfig | None = None):
        self.vault_path = vault_path
        self.config = config or WikiConfig()
        self.wiki_dir = os.path.join(vault_path, self.config.wiki_dir)

    def lint(self, stale_days: int = 30) -> LintResult:
        """Run all lint checks."""
        result = LintResult()

        if not os.path.isdir(self.wiki_dir):
            result.errors.append(f"Wiki directory not found: {self.wiki_dir}")
            return result

        # Scan all wiki pages
        pages = {}          # title -> filepath
        links_from = {}     # filepath -> set of link targets
        all_links = set()   # all link targets
        pages_by_canonical: dict[str, list[dict]] = {}
        page_count = 0

        for dir_name in self.config.page_dirs():
            dir_path = os.path.join(self.wiki_dir, dir_name)
            if not os.path.isdir(dir_path):
                continue
            for filename in os.listdir(dir_path):
                if not filename.endswith(".md"):
                    continue
                filepath = os.path.join(dir_path, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Extract title from frontmatter or first heading
                    title = self._extract_title(content, filename)
                    pages[title] = filepath
                    page_count += 1
                    canonical = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.casefold())
                    page_type = ""
                    if content.startswith("---"):
                        end = content.find("---", 3)
                        if end >= 0:
                            try:
                                page_type = str((yaml.safe_load(content[3:end]) or {}).get("type") or "")
                            except yaml.YAMLError:
                                pass
                    duplicate_key = f"{page_type}:{canonical}"
                    pages_by_canonical.setdefault(duplicate_key, []).append({
                        "title": title,
                        "path": os.path.relpath(filepath, self.wiki_dir).replace("\\", "/"),
                    })

                    # Extract wikilinks
                    links = set(WIKILINK_RE.findall(content))
                    links_from[filepath] = links
                    all_links.update(links)

                except Exception as e:
                    result.errors.append(f"Error reading {filepath}: {e}")

        result.total_pages = page_count
        result.duplicate_candidates = [
            {
                "canonical_title": sorted(items, key=lambda item: (len(item["title"]), item["title"].casefold()))[0]["title"],
                "pages": sorted(item["path"] for item in items),
            }
            for items in pages_by_canonical.values()
            if len(items) > 1
        ]
        semantic_path = os.path.join(self.wiki_dir, ".semantic-review.json")
        try:
            with open(semantic_path, "r", encoding="utf-8") as handle:
                semantic = json.load(handle)
            result.semantic_candidates = list(semantic.get("issues") or [])
            result.contradiction_candidates = sorted({
                str(page)
                for item in result.semantic_candidates
                if item.get("type") == "contradiction"
                for page in item.get("pages") or []
            })
        except (OSError, json.JSONDecodeError):
            pass

        try:
            from .index import WikiIndexer

            if os.path.isfile(self.config.index_path(self.vault_path)):
                indexed = WikiIndexer(self.vault_path, self.config).read_index()
                indexed_titles = {title for entries in indexed.values() for title in entries}
                result.index_mismatches = sorted(
                    {f"unindexed:{title}" for title in pages if title not in indexed_titles}
                    | {f"missing:{title}" for title in indexed_titles if title not in pages}
                )
        except (OSError, ValueError):
            result.index_mismatches = ["index_unreadable"]

        # Find broken links and missing pages
        canonical_pages = {
            re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.casefold()): title
            for title in pages
        }
        for filepath, links in links_from.items():
            for link in links:
                canonical_link = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", link.casefold())
                if canonical_link not in canonical_pages:
                    result.broken_links.append({
                        "source": filepath,
                        "target": link,
                    })
                    if link not in result.missing_pages:
                        result.missing_pages.append(link)

        # Find orphan pages (no inbound links, except source pages)
        pages_with_inbound = set()
        for links in links_from.values():
            pages_with_inbound.update(
                re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", link.casefold()) for link in links
            )

        for title, filepath in pages.items():
            # Source pages are not orphans by definition
            if "source" in filepath.lower() or f"{os.sep}{self.config.note_dir}{os.sep}" in filepath:
                continue
            # Index and log are not orphans
            if title in ("Wiki Index", "Wiki Log"):
                continue
            canonical_title = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", title.casefold())
            if canonical_title not in pages_with_inbound:
                result.orphan_pages.append(title)

        # Find stale pages
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        for title, filepath in pages.items():
            if f"{os.sep}{self.config.note_dir}{os.sep}" in filepath:
                continue
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc)
                if mtime < cutoff:
                    result.stale_pages.append(title)
            except Exception:
                pass

        return result

    def semantic_review(self, llm_provider) -> dict:
        """Generate advisory semantic issues and persist them without changing Wiki pages."""
        if llm_provider is None:
            raise ValueError("No configured model is available for semantic Wiki review")
        excerpts = []
        for dir_name in self.config.page_dirs():
            directory = os.path.join(self.wiki_dir, dir_name)
            if not os.path.isdir(directory):
                continue
            for filename in sorted(os.listdir(directory), key=str.casefold):
                if not filename.endswith(".md"):
                    continue
                path = os.path.join(directory, filename)
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        content = handle.read()
                except OSError:
                    continue
                title = self._extract_title(content, filename)
                excerpts.append(f"## {title}\n{content[:1200]}")
                if sum(len(item) for item in excerpts) >= 30000:
                    break
            if sum(len(item) for item in excerpts) >= 30000:
                break
        if not excerpts:
            payload = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "issues": []}
        else:
            from .compiler import _parse_llm_json

            started = time.perf_counter()
            response = llm_provider.complete([{
                "role": "user",
                "content": SEMANTIC_PROMPT.format(pages="\n\n".join(excerpts)),
            }])
            from service.usage_service import UsageService
            UsageService().record(
                response,
                subsystem="wiki",
                operation="wiki_semantic_review",
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            parsed = _parse_llm_json(response.content or "")
            if not isinstance(parsed, dict) or not isinstance(parsed.get("issues"), list):
                raise ValueError("The model did not return a valid semantic Wiki review")
            issues = []
            for item in parsed["issues"][:50]:
                if not isinstance(item, dict) or item.get("type") not in {
                    "contradiction", "stale", "missing-knowledge",
                }:
                    continue
                reason = str(item.get("reason") or "").strip()
                pages = [str(page).strip() for page in item.get("pages") or [] if str(page).strip()]
                if reason:
                    issues.append({"type": item["type"], "pages": pages, "reason": reason})
            payload = {
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "issues": issues,
            }
        os.makedirs(self.wiki_dir, exist_ok=True)
        temporary = os.path.join(self.wiki_dir, ".semantic-review.json.tmp")
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, os.path.join(self.wiki_dir, ".semantic-review.json"))
        return payload

    def _extract_title(self, content: str, filename: str) -> str:
        """Extract title from frontmatter or first heading."""
        # Try frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                try:
                    meta = yaml.safe_load(content[3:end])
                    if meta and meta.get("title"):
                        return meta["title"]
                except Exception:
                    pass

        # Try first # heading
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()

        # Fallback to filename
        return filename.replace(".md", "")

    def format_result(self, result: LintResult) -> str:
        """Format lint result as human-readable text."""
        lines = [f"Wiki 健康检查：共 {result.total_pages} 个页面"]

        if result.healthy:
            lines.append("✓ 一切正常")
            return "\n".join(lines)

        if result.orphan_pages:
            lines.append(f"\n孤立页面（{len(result.orphan_pages)}）：无入链引用")
            for p in result.orphan_pages[:10]:
                lines.append(f"  - {p}")

        if result.broken_links:
            lines.append(f"\n断链（{len(result.broken_links)}）：目标页面不存在")
            for bl in result.broken_links[:10]:
                src = os.path.basename(bl["source"])
                lines.append(f"  - {src} → [[{bl['target']}]]")

        if result.stale_pages:
            lines.append(f"\n过期页面（{len(result.stale_pages)}）：超过 30 天未更新")
            for p in result.stale_pages[:10]:
                lines.append(f"  - {p}")

        if result.errors:
            lines.append(f"\n错误（{len(result.errors)}）：")
            for e in result.errors[:5]:
                lines.append(f"  - {e}")

        return "\n".join(lines)
