"""Persistent memory system for bobodan agent.

Stores user preferences, learning context, and feedback as individual
Markdown files with YAML frontmatter. An auto-generated MEMORY.md index
is injected into the system prompt so the agent can recall across sessions.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import yaml

from core.skills import parse_frontmatter

logger = logging.getLogger(__name__)

MEMORY_MARKER = "<!-- [memory_prompt] -->"
MEMORY_FILENAME = "MEMORY.md"
MEMORY_DIR = "memory"
MEMORY_INDEX_FILE = "memory_index.json"

VALID_TYPES = {"user", "feedback", "project", "reference"}


@dataclass
class MemoryEntry:
    name: str
    description: str
    type: str  # user | feedback | project | reference
    content: str
    file_path: str = ""
    created: str = ""
    updated: str = ""

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not self.created:
            self.created = now
        if not self.updated:
            self.updated = now
        if self.type not in VALID_TYPES:
            self.type = "user"


class MemoryManager:
    """Manages persistent memories stored as Markdown files."""

    def __init__(self, workspace_dir: str, base_dir: str = ".bobodan"):
        self.workspace_root = workspace_dir
        self.base_dir = os.path.join(workspace_dir, base_dir)
        self.memory_dir = os.path.join(self.base_dir, MEMORY_DIR)
        self.index_path = os.path.join(self.base_dir, MEMORY_INDEX_FILE)
        self.entries: list[MemoryEntry] = []

    def _ensure_dirs(self) -> None:
        os.makedirs(self.memory_dir, exist_ok=True)

    def _entry_path(self, name: str) -> str:
        safe_name = name.replace("/", "_").replace("\\", "_").replace(" ", "-")
        return os.path.join(self.memory_dir, f"{safe_name}.md")

    def _build_frontmatter(self, entry: MemoryEntry) -> str:
        meta = {
            "name": entry.name,
            "description": entry.description,
            "type": entry.type,
            "created": entry.created,
            "updated": entry.updated,
        }
        return f"---\n{yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()}\n---\n\n"

    def load_entries(self) -> list[MemoryEntry]:
        """Scan memory directory and parse all .md files."""
        self.entries = []
        if not os.path.isdir(self.memory_dir):
            return self.entries

        for filename in sorted(os.listdir(self.memory_dir)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self.memory_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    raw = f.read()
            except OSError:
                logger.warning("Failed to read memory file: %s", filepath)
                continue

            meta = parse_frontmatter(raw)
            # Extract body (everything after frontmatter)
            body = raw
            if raw.startswith("---"):
                end = raw.find("---", 3)
                if end != -1:
                    body = raw[end + 3:].strip()

            name = meta.get("name") or filename.replace(".md", "")
            description = meta.get("description") or ""
            entry_type = meta.get("type") or "user"
            created = meta.get("created") or ""
            updated = meta.get("updated") or ""

            self.entries.append(MemoryEntry(
                name=name,
                description=description,
                type=entry_type,
                content=body,
                file_path=filepath,
                created=created,
                updated=updated,
            ))

        return self.entries

    def save(self, name: str, description: str, content: str,
             entry_type: str = "user") -> MemoryEntry:
        """Save or update a memory entry."""
        self._ensure_dirs()
        self.load_entries()

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        existing = self.get_entry(name)

        if existing:
            existing.description = description or existing.description
            existing.content = content
            existing.type = entry_type if entry_type in VALID_TYPES else existing.type
            existing.updated = now
            entry = existing
        else:
            entry = MemoryEntry(
                name=name,
                description=description,
                type=entry_type,
                content=content,
                created=now,
                updated=now,
            )
            self.entries.append(entry)

        # Write file
        filepath = self._entry_path(name)
        entry.file_path = filepath
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self._build_frontmatter(entry) + content + "\n")

        # Update index
        self._update_index()

        # Update vector store
        self._update_vector_store(entry)

        logger.info("Memory saved: %s (%s)", name, entry_type)
        return entry

    def get_entry(self, name: str) -> MemoryEntry | None:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def forget(self, name: str) -> bool:
        """Remove a memory entry by name."""
        self.load_entries()
        entry = self.get_entry(name)
        if not entry:
            return False

        # Delete file
        if entry.file_path and os.path.exists(entry.file_path):
            os.remove(entry.file_path)

        # Remove from list
        self.entries = [e for e in self.entries if e.name != name]

        # Update index
        self._update_index()

        # Remove from vector store
        self._remove_from_vector_store(name)

        logger.info("Memory forgotten: %s", name)
        return True

    def list_entries(self) -> list[MemoryEntry]:
        if not self.entries:
            self.load_entries()
        return self.entries

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search memories using vector similarity."""
        try:
            from rag.vector_store import LocalVectorStore
            store = LocalVectorStore(self.index_path)
            store.load()
            if not store.chunks:
                return []
            return store.search(query, top_k=top_k)
        except Exception as e:
            logger.warning("Memory search failed: %s", e)
            return []

    def _update_index(self) -> None:
        """Update the MEMORY.md index file."""
        index_path = os.path.join(self.base_dir, MEMORY_FILENAME)
        lines = [
            "# Memory Index",
            "",
            "| Name | Type | Description | Updated |",
            "|------|------|-------------|---------|",
        ]
        for entry in sorted(self.entries, key=lambda e: e.name):
            lines.append(
                f"| {entry.name} | {entry.type} | {entry.description} | {entry.updated} |"
            )
        lines.append("")
        lines.append(f"*{len(self.entries)} memories stored*")
        lines.append("")

        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _update_vector_store(self, entry: MemoryEntry) -> None:
        """Add or update entry in the vector store."""
        try:
            from rag.vector_store import LocalVectorStore
            from rag.chunker import chunk_text

            store = LocalVectorStore(self.index_path)
            store.load()

            # Remove old chunks for this entry first
            source_prefix = f"memory://{entry.name}"
            store.chunks = [
                c for c in store.chunks
                if not c.get("source", "").startswith(source_prefix)
            ]

            # Chunk and add new content
            full_text = f"{entry.name}: {entry.description}\n\n{entry.content}"
            chunks = chunk_text(
                full_text,
                source=source_prefix,
                metadata={"name": entry.name, "type": entry.type},
            )

            for chunk in chunks:
                item = {
                    "id": chunk.id,
                    "text": chunk.text,
                    "source": chunk.source,
                    "metadata": chunk.metadata,
                    "vector": store.embedding_provider.embed(chunk.text),
                }
                store.chunks.append(item)

            store.save()
        except Exception as e:
            logger.warning("Failed to update memory vector store: %s", e)

    def _remove_from_vector_store(self, name: str) -> None:
        """Remove all chunks for a memory entry from the vector store."""
        try:
            from rag.vector_store import LocalVectorStore

            store = LocalVectorStore(self.index_path)
            store.load()

            source_prefix = f"memory://{name}"
            store.chunks = [
                c for c in store.chunks
                if not c.get("source", "").startswith(source_prefix)
            ]
            store.save()
        except Exception as e:
            logger.warning("Failed to remove from memory vector store: %s", e)

    def build_memory_prompt(self) -> str | None:
        """Build a system prompt fragment containing all memories.

        Returns None if no memories exist. Uses MEMORY_MARKER for idempotent
        injection (same pattern as SKILLS_PROMPT_MARKER).
        """
        entries = self.load_entries()
        if not entries:
            return None

        lines = [
            MEMORY_MARKER,
            "",
            "The following memories about the user and project context have been saved.",
            "Use this information to personalize your responses and avoid asking",
            "for information the user has already provided.",
            "",
            "<memories>",
        ]

        by_type: dict[str, list[MemoryEntry]] = {}
        for entry in entries:
            by_type.setdefault(entry.type, []).append(entry)

        type_labels = {
            "user": "User Profile",
            "feedback": "User Feedback",
            "project": "Project Context",
            "reference": "References",
        }

        for entry_type in ["user", "feedback", "project", "reference"]:
            group = by_type.get(entry_type, [])
            if not group:
                continue
            label = type_labels.get(entry_type, entry_type)
            lines.append(f"  <memory_group type=\"{entry_type}\" label=\"{label}\">")
            for entry in group:
                lines.append(f"    <memory name=\"{entry.name}\">")
                lines.append(f"      <description>{entry.description}</description>")
                lines.append(f"      <content>{entry.content}</content>")
                lines.append(f"    </memory>")
            lines.append(f"  </memory_group>")

        lines.append("</memories>")
        lines.append("")
        return "\n".join(lines)

    def get_stats(self) -> dict:
        """Return memory system statistics."""
        entries = self.load_entries()
        by_type: dict[str, int] = {}
        for entry in entries:
            by_type[entry.type] = by_type.get(entry.type, 0) + 1

        # Check vector store
        vector_chunks = 0
        try:
            from rag.vector_store import LocalVectorStore
            store = LocalVectorStore(self.index_path)
            store.load()
            vector_chunks = len(store.chunks)
        except Exception:
            pass

        return {
            "total": len(entries),
            "by_type": by_type,
            "vector_chunks": vector_chunks,
            "base_dir": self.base_dir,
            "memory_dir": self.memory_dir,
        }
