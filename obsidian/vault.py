import hashlib
import os
from dataclasses import dataclass

from .parser import ParsedNote, parse_markdown_note


SKIP_DIRS = {".git", ".obsidian", ".trash", "__pycache__", ".venv", "venv"}


@dataclass
class ScannedNote:
    """A Markdown note discovered in an Obsidian vault."""

    abs_path: str
    rel_path: str
    content_hash: str
    note: ParsedNote


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scan_vault(vault_path: str) -> list[ScannedNote]:
    """Scan a vault directory and parse all Markdown notes."""
    notes: list[ScannedNote] = []
    vault_path = os.path.abspath(vault_path)

    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".")]
        for filename in files:
            if not filename.lower().endswith(".md"):
                continue
            abs_path = os.path.join(root, filename)
            rel_path = os.path.relpath(abs_path, vault_path).replace(os.sep, "/")
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(abs_path, "r", encoding="utf-8-sig") as f:
                    content = f.read()

            parsed = parse_markdown_note(content, rel_path)
            notes.append(
                ScannedNote(
                    abs_path=abs_path,
                    rel_path=rel_path,
                    content_hash=_hash_text(content),
                    note=parsed,
                )
            )

    return sorted(notes, key=lambda item: item.rel_path.casefold())
