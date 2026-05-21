"""Daily memory file management.

Daily memories are stored as Markdown files in .bobodan/daily/YYYY-MM-DD.md.
Each file has YAML frontmatter with date and tags, followed by timestamped entries.
"""

import os
import logging
from datetime import datetime, timezone, timedelta

import yaml

from core.skills import parse_frontmatter

logger = logging.getLogger(__name__)

DAILY_DIR = "daily"


class DailyMemoryManager:
    """Manages daily memory files in .bobodan/daily/."""

    def __init__(self, workspace: str, base_dir: str = ".bobodan"):
        self.daily_dir = os.path.join(workspace, base_dir, DAILY_DIR)
        os.makedirs(self.daily_dir, exist_ok=True)

    def _file_path(self, date_str: str) -> str:
        return os.path.join(self.daily_dir, f"{date_str}.md")

    def _today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _yesterday_str(self) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    def append(self, content: str, date: str | None = None,
               tags: list[str] | None = None) -> str:
        """Append content to a daily memory file.

        Args:
            content: Text content to append (will be wrapped in a timestamped section).
            date: YYYY-MM-DD string, defaults to today UTC.
            tags: Optional tags for the file frontmatter.

        Returns:
            Path to the updated file.
        """
        date = date or self._today_str()
        filepath = self._file_path(date)
        now_time = datetime.now(timezone.utc).strftime("%H:%M")

        section = f"\n## {now_time}\n{content.strip()}\n"

        if os.path.exists(filepath):
            # Append to existing file
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(section)
            # Update tags in frontmatter if new tags provided
            if tags:
                self._update_frontmatter_tags(filepath, tags)
        else:
            # Create new file with frontmatter
            tags = tags or []
            frontmatter = self._build_frontmatter(date, tags)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(frontmatter + section)

        logger.info("Daily memory appended: %s", filepath)
        return filepath

    def read(self, date: str) -> str:
        """Read a daily memory file by date string (YYYY-MM-DD)."""
        filepath = self._file_path(date)
        if not os.path.exists(filepath):
            return ""
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def get_today(self) -> str:
        """Read today's daily memory content."""
        return self.read(self._today_str())

    def get_yesterday(self) -> str:
        """Read yesterday's daily memory content."""
        return self.read(self._yesterday_str())

    def list_recent(self, days: int = 7) -> list[dict]:
        """List daily memory files from the last N days.

        Returns list of {date, path, exists, preview}.
        """
        results = []
        today = datetime.now(timezone.utc).date()
        for i in range(days):
            d = today - timedelta(days=i)
            date_str = d.strftime("%Y-%m-%d")
            filepath = self._file_path(date_str)
            exists = os.path.exists(filepath)
            preview = ""
            if exists:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        raw = f.read()
                    # Strip frontmatter for preview
                    body = raw
                    if raw.startswith("---"):
                        end = raw.find("---", 3)
                        if end != -1:
                            body = raw[end + 3:].strip()
                    preview = body[:200].replace("\n", " ")
                except OSError:
                    pass
            results.append({
                "date": date_str,
                "path": filepath,
                "exists": exists,
                "preview": preview,
            })
        return results

    def get_all_dates(self) -> list[str]:
        """List all dates that have daily memory files."""
        if not os.path.isdir(self.daily_dir):
            return []
        dates = []
        for filename in sorted(os.listdir(self.daily_dir)):
            if filename.endswith(".md"):
                dates.append(filename.replace(".md", ""))
        return dates

    def _build_frontmatter(self, date: str, tags: list[str]) -> str:
        meta = {"date": date, "tags": tags}
        fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
        return f"---\n{fm}\n---\n\n"

    def _update_frontmatter_tags(self, filepath: str, new_tags: list[str]) -> None:
        """Merge new tags into existing frontmatter."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = f.read()
            meta = parse_frontmatter(raw)
            existing_tags = meta.get("tags", [])
            if isinstance(existing_tags, str):
                existing_tags = [existing_tags]
            merged = list(set(existing_tags) | set(new_tags))
            meta["tags"] = merged

            # Rebuild file
            body = raw
            if raw.startswith("---"):
                end = raw.find("---", 3)
                if end != -1:
                    body = raw[end + 3:]

            fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"---\n{fm}\n---\n{body}")
        except Exception as e:
            logger.warning("Failed to update frontmatter tags: %s", e)
