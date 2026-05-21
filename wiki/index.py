"""Wiki index and log management.

index.md — content catalog organized by category (entities, concepts, sources).
log.md — append-only chronological record of operations.
"""

import os
import logging
from datetime import datetime, timezone

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
