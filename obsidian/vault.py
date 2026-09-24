import hashlib
import json
import os
from dataclasses import dataclass

from .parser import ParsedNote, parse_markdown_note
from .scan_policy import is_repo_metadata


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


def scan_vault(
    vault_path: str,
    errors: list[str] | None = None,
    *,
    skipped: list[str] | None = None,
) -> list[ScannedNote]:
    """Scan a vault directory and parse all Markdown notes.

    P0-12: unreadable directories and files are reported through `errors`
    rather than disappearing, because the sync treats a source it cannot see
    as deleted.
    """
    notes: list[ScannedNote] = []
    vault_path = os.path.abspath(vault_path)
    portable_library = os.path.isfile(os.path.join(vault_path, "BOBODAN_LIBRARY.yaml"))
    registered_source_names: set[str] = set()
    if portable_library:
        roots_path = os.path.join(vault_path, ".bobodan", "source_roots.json")
        try:
            with open(roots_path, "r", encoding="utf-8") as handle:
                roots = json.load(handle)
            for source_root in roots.get("course_dirs") or []:
                source_root = str(source_root)
                absolute = os.path.abspath(
                    source_root if os.path.isabs(source_root) else os.path.join(vault_path, source_root)
                )
                if not os.path.isdir(absolute) and os.path.isabs(source_root):
                    absolute = os.path.join(vault_path, os.path.basename(os.path.normpath(source_root)))
                if os.path.dirname(absolute) == vault_path:
                    registered_source_names.add(os.path.basename(absolute))
        except (OSError, json.JSONDecodeError):
            pass

    def _on_error(exc: OSError) -> None:
        if errors is not None:
            errors.append(f"{getattr(exc, 'filename', vault_path)}: {exc}")

    for root, dirs, files in os.walk(vault_path, onerror=_on_error):
        dirs[:] = [
            name for name in dirs
            if name not in SKIP_DIRS
            and not name.startswith(".")
            # `wiki/` holds AI 生成页：2026-09-24 用户决定 wiki 停用，生成页
            # 不再作为资料进入索引与检索（文件保留在磁盘上）。
            and not (portable_library and name in {"raw", "templates", "wiki"})
            and not (portable_library and root == vault_path and name in registered_source_names)
        ]
        for filename in files:
            if not filename.lower().endswith(".md"):
                continue
            if portable_library and root == vault_path and filename in {"WIKI_SCHEMA.md"}:
                continue
            if is_repo_metadata(filename):
                if skipped is not None:
                    skipped.append(os.path.relpath(
                        os.path.join(root, filename), vault_path
                    ).replace(os.sep, "/"))
                continue
            abs_path = os.path.join(root, filename)
            rel_path = os.path.relpath(abs_path, vault_path).replace(os.sep, "/")
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(abs_path, "r", encoding="utf-8-sig") as f:
                    content = f.read()
            except OSError as exc:
                if errors is not None:
                    errors.append(f"{rel_path}: {exc}")
                continue

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
