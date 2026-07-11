"""Wiki index and log management.

index.md — content catalog organized by category (entities, concepts, sources).
log.md — append-only chronological record of operations.
"""

import os
import logging
import re
import shutil
import unicodedata
from datetime import datetime, timezone

import yaml

from .schema import WikiPage, WikiConfig, CompileResult

logger = logging.getLogger(__name__)


class WikiIndexer:
    """Manages wiki index.md and log.md files."""

    def __init__(self, vault_path: str, config: WikiConfig | None = None):
        self.vault_path = vault_path
        self.config = config or WikiConfig()
        self.wiki_dir = os.path.join(vault_path, self.config.wiki_dir)

    def update_index(self, pages: list[WikiPage]) -> None:
        """Update index.md with new pages. Preserves existing entries."""
        os.makedirs(self.wiki_dir, exist_ok=True)
        index_path = self.config.index_path(self.vault_path)

        # Load existing index to preserve entries
        existing = self._load_existing_index(index_path)

        # Merge new pages into existing entries (by title)
        for page in pages:
            key = page.page_type
            if key not in existing:
                existing[key] = {}
            existing[key][page.title] = {
                "tags": page.tags,
                "sources": page.sources,
                "updated": page.updated or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }

        # Write index
        lines = [
            "# Wiki Index",
            "",
            f"_Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}_",
            "",
        ]

        type_labels = {
            "wiki_entity": "实体",
            "wiki_concept": "概念",
            "wiki_source": "来源",
        }

        for page_type in ["wiki_entity", "wiki_concept", "wiki_source"]:
            entries = existing.get(page_type, {})
            if not entries:
                continue
            label = type_labels.get(page_type, page_type)
            lines.append(f"## {label}")
            lines.append("")
            for title, meta in sorted(entries.items()):
                tags_str = ""
                if meta.get("tags"):
                    tags_str = f" `{', '.join(meta['tags'][:3])}`"
                lines.append(f"- [[{title}]]{tags_str}")
            lines.append("")

        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def rebuild_index(self, pages: list[WikiPage]) -> None:
        """Replace index.md with entries from the current canonical pages only."""
        index_path = self.config.index_path(self.vault_path)
        if os.path.exists(index_path):
            os.remove(index_path)
        self.update_index(pages)

    def append_log(self, action: str, source: str, result: CompileResult | None = None) -> None:
        """Append an entry to log.md."""
        os.makedirs(self.wiki_dir, exist_ok=True)
        log_path = self.config.log_path(self.vault_path)

        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%d %H:%M")

        lines = [f"## [{timestamp}] {action} | {os.path.basename(source)}"]

        if result:
            if result.entities_count:
                lines.append(f"- 生成实体：{result.entities_count} 个")
            if result.concepts_count:
                lines.append(f"- 生成概念：{result.concepts_count} 个")
            if result.sources_count:
                lines.append(f"- 生成来源页：{result.sources_count} 个")
            if result.skipped:
                lines.append(f"- 跳过（未变更）：{len(result.skipped)} 个")
            if result.errors:
                for err in result.errors:
                    lines.append(f"- 错误：{err.get('error', '?')}")

        lines.append("")

        # Create file with header if it doesn't exist
        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("# Wiki Log\n\n")

        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def read_index(self) -> dict:
        """Read and parse index.md. Returns {type: {title: meta}}."""
        index_path = self.config.index_path(self.vault_path)
        return self._load_existing_index(index_path)

    def read_log(self, limit: int = 20) -> list[str]:
        """Read recent log entries."""
        log_path = self.config.log_path(self.vault_path)
        if not os.path.exists(log_path):
            return []
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Split by ## headers
        entries = []
        for block in content.split("\n## "):
            block = block.strip()
            if block and block != "Wiki Log":
                entries.append(f"## {block}")
        return entries[-limit:]

    def _load_existing_index(self, index_path: str) -> dict:
        """Parse existing index.md into structured data."""
        if not os.path.exists(index_path):
            return {}

        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()

        result = {}
        current_type = None
        type_map = {"实体": "wiki_entity", "概念": "wiki_concept", "来源": "wiki_source"}

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("## "):
                label = line[3:].strip()
                current_type = type_map.get(label)
            elif line.startswith("- [[") and current_type:
                # Parse: - [[Title]] `tags`
                end = line.find("]]")
                if end != -1:
                    title = line[4:end]
                    if current_type not in result:
                        result[current_type] = {}
                    result[current_type][title] = {"tags": [], "sources": [], "updated": ""}

        return result


def _canonical_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title or "").casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def _read_generated_page(path: str) -> tuple[dict, str] | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return None
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    try:
        metadata = yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        return None
    if metadata.get("generated_by") != "bobodan":
        return None
    return metadata, content[end + 3:].strip()


def archive_duplicate_pages(
    vault_path: str,
    archive_root: str,
    timestamp: str | None = None,
) -> dict:
    """Archive stale Bobodan-generated Wiki duplicates and rebuild the index."""
    config = WikiConfig()
    wiki_dir = os.path.join(vault_path, config.wiki_dir)
    if not os.path.isdir(wiki_dir):
        return {"archived": [], "canonical": 0, "archive_dir": None}

    groups: dict[str, list[tuple[str, dict, str]]] = {}
    for directory in (config.entities_path(vault_path), config.concepts_path(vault_path)):
        if not os.path.isdir(directory):
            continue
        for filename in os.listdir(directory):
            if not filename.endswith(".md"):
                continue
            path = os.path.join(directory, filename)
            parsed = _read_generated_page(path)
            if not parsed:
                continue
            metadata, body = parsed
            title = str(metadata.get("title") or os.path.splitext(filename)[0])
            groups.setdefault(_canonical_title(title), []).append((path, metadata, body))

    canonical: list[tuple[str, dict, str]] = []
    stale: list[tuple[str, dict, str]] = []
    for pages in groups.values():
        pages.sort(key=lambda item: (
            not bool(item[1].get("indexable")),
            item[1].get("type") != "wiki_concept",
            item[0].casefold(),
        ))
        canonical.append(pages[0])
        stale.extend(pages[1:])

    archive_dir = None
    archived = []
    if stale:
        stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_dir = os.path.join(archive_root, stamp)
        for path, _metadata, _body in stale:
            relative = os.path.relpath(path, wiki_dir)
            target = os.path.join(archive_dir, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(path, target)
            archived.append(relative.replace("\\", "/"))

    pages = [WikiPage(
        title=str(metadata.get("title") or os.path.splitext(os.path.basename(path))[0]),
        page_type=str(metadata.get("type") or "wiki_entity"),
        content=body,
        tags=list(metadata.get("tags") or []),
        sources=list(metadata.get("sources") or []),
        source_hash=str(metadata.get("source_hash") or ""),
        indexable=bool(metadata.get("indexable", False)),
        created=str(metadata.get("created") or ""),
        updated=str(metadata.get("updated") or ""),
    ) for path, metadata, body in canonical]
    WikiIndexer(vault_path, config).rebuild_index(pages)
    return {"archived": archived, "canonical": len(pages), "archive_dir": archive_dir}
