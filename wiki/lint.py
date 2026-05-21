"""Wiki health checker — finds orphans, broken links, missing pages, stale pages."""

import os
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import yaml

from .schema import WikiConfig

logger = logging.getLogger(__name__)

WIKILINK_RE = re.compile(r'\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]')


@dataclass
class LintResult:
    """Result of a wiki health check."""
    total_pages: int = 0
    orphan_pages: list[str] = field(default_factory=list)       # 无入链
    broken_links: list[dict] = field(default_factory=list)      # 指向不存在页面
    missing_pages: list[str] = field(default_factory=list)      # 被引用但不存在
    stale_pages: list[str] = field(default_factory=list)        # 超过 N 天未更新
    errors: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.orphan_pages and not self.broken_links and not self.missing_pages


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

        for dir_name in [self.config.entity_dir, self.config.concept_dir]:
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

                    # Extract wikilinks
                    links = set(WIKILINK_RE.findall(content))
                    links_from[filepath] = links
                    all_links.update(links)

                except Exception as e:
                    result.errors.append(f"Error reading {filepath}: {e}")

        result.total_pages = len(pages)

        # Find broken links and missing pages
        for filepath, links in links_from.items():
            for link in links:
                if link not in pages:
                    result.broken_links.append({
                        "source": filepath,
                        "target": link,
                    })
                    if link not in result.missing_pages:
                        result.missing_pages.append(link)

        # Find orphan pages (no inbound links, except source pages)
        pages_with_inbound = set()
        for links in links_from.values():
            pages_with_inbound.update(links)

        for title, filepath in pages.items():
            # Source pages are not orphans by definition
            if "source" in filepath.lower():
                continue
            # Index and log are not orphans
            if title in ("Wiki Index", "Wiki Log"):
                continue
            if title not in pages_with_inbound:
                result.orphan_pages.append(title)

        # Find stale pages
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        for title, filepath in pages.items():
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc)
                if mtime < cutoff:
                    result.stale_pages.append(title)
            except Exception:
                pass

        return result

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
