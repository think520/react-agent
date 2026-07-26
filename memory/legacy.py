"""Read-only access to the retired Markdown memory format.

Legacy files are user data.  They remain readable for preview/import, but this
module intentionally exposes no write, delete, indexing, or prompt-building
operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.skills import parse_frontmatter


@dataclass(frozen=True)
class LegacyMemoryEntry:
    name: str
    description: str
    type: str
    content: str
    file_path: str
    created: str = ""
    updated: str = ""


class LegacyMemoryReader:
    """Parse ``.bobodan/memory/*.md`` without mutating legacy data."""

    def __init__(self, workspace: str, base_dir: str = ".bobodan") -> None:
        self.workspace = Path(workspace)
        self.base_dir = self.workspace / base_dir
        self.memory_dir = self.base_dir / "memory"
        self.daily_dir = self.base_dir / "daily"

    def list_entries(self) -> list[LegacyMemoryEntry]:
        if not self.memory_dir.is_dir():
            return []
        entries: list[LegacyMemoryEntry] = []
        for path in sorted(self.memory_dir.glob("*.md")):
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            metadata = parse_frontmatter(raw)
            body = raw
            if raw.startswith("---"):
                end = raw.find("---", 3)
                if end >= 0:
                    body = raw[end + 3:].strip()
            entries.append(LegacyMemoryEntry(
                name=str(metadata.get("name") or path.stem),
                description=str(metadata.get("description") or ""),
                type=str(metadata.get("type") or "user"),
                content=body,
                file_path=str(path),
                created=str(metadata.get("created") or ""),
                updated=str(metadata.get("updated") or ""),
            ))
        return entries

    def list_daily_files(self) -> list[str]:
        if not self.daily_dir.is_dir():
            return []
        return sorted(path.name for path in self.daily_dir.glob("*.md"))
