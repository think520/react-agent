import os
import re
from dataclasses import dataclass, field
from typing import Any

import yaml


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
TAG_RE = re.compile(r"(?<![\w/])#([\w\-/\u4e00-\u9fff]+)")


@dataclass(frozen=True)
class WikiLink:
    """An Obsidian wiki link, including optional display alias."""

    target: str
    alias: str | None = None


@dataclass
class ParsedNote:
    """Structured fields extracted from an Obsidian Markdown note."""

    path: str
    title: str
    body: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    links: list[WikiLink] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    course: str | None = None
    chapter: str | None = None


def _normalize_scalar(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        values = value
    else:
        values = [value]
    result = []
    for item in values:
        text = _normalize_scalar(item)
        if text:
            result.append(text)
    return result


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Return YAML frontmatter and body from Markdown content."""
    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    raw = match.group(1)
    try:
        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return parsed, content[match.end():]


def extract_title(body: str, path: str, frontmatter: dict[str, Any]) -> str:
    """Pick the canonical note title from metadata, heading, or file name."""
    for key in ("canonical", "title", "name"):
        value = _normalize_scalar(frontmatter.get(key))
        if value:
            return value

    match = TITLE_RE.search(body)
    if match:
        return match.group(1).strip()

    return os.path.splitext(os.path.basename(path))[0]


def extract_wikilinks(body: str) -> list[WikiLink]:
    links = []
    for target, alias in WIKILINK_RE.findall(body):
        clean_target = target.strip()
        clean_alias = alias.strip() if alias and alias.strip() else None
        if clean_target:
            links.append(WikiLink(target=clean_target, alias=clean_alias))
    return links


def extract_tags(body: str, frontmatter: dict[str, Any]) -> list[str]:
    tags = []
    tags.extend(tag.strip() for tag in TAG_RE.findall(body) if tag.strip())
    tags.extend(_normalize_list(frontmatter.get("tags")))
    tags.extend(_normalize_list(frontmatter.get("tag")))
    return _dedupe_preserve_order(tags)


def parse_markdown_note(content: str, path: str) -> ParsedNote:
    """Parse a Markdown note into RAG and graph-friendly metadata."""
    frontmatter, body = split_frontmatter(content)
    title = extract_title(body, path, frontmatter)
    links = extract_wikilinks(body)

    aliases = []
    aliases.extend(_normalize_list(frontmatter.get("aliases")))
    aliases.extend(_normalize_list(frontmatter.get("alias")))
    aliases.extend(link.alias for link in links if link.alias)
    aliases = _dedupe_preserve_order([alias for alias in aliases if alias])

    return ParsedNote(
        path=path,
        title=title,
        body=body.strip(),
        frontmatter=frontmatter,
        links=links,
        tags=extract_tags(body, frontmatter),
        aliases=aliases,
        course=_normalize_scalar(frontmatter.get("course")),
        chapter=_normalize_scalar(frontmatter.get("chapter")),
    )
