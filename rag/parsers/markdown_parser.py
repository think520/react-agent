"""Markdown parser — heading-aware section splitting.

Uses existing obsidian.parser for frontmatter extraction.
Splits on #/##/### headings into SourceSection objects.
"""

from __future__ import annotations

import re
from pathlib import Path

from rag.source_section import SourceSection

# Heading regex: matches # through ######
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def parse(path: str | Path, base_dir: str | Path = ".") -> list[SourceSection]:
    """Parse a Markdown file into heading-aware SourceSections."""
    path = Path(path)
    base_dir = Path(base_dir)

    try:
        relative = path.relative_to(base_dir)
    except ValueError:
        relative = path

    source = str(relative).replace("\\", "/")

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="utf-8", errors="replace")

    return _split_markdown(content, source, path)


def _split_markdown(content: str, source: str, path: Path) -> list[SourceSection]:
    """Split Markdown content into sections by headings."""
    # Extract frontmatter
    from obsidian.parser import split_frontmatter, extract_title

    frontmatter, body = split_frontmatter(content)
    doc_title = extract_title(body, str(path), frontmatter)
    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    course = frontmatter.get("course")

    # Find all heading positions
    headings = [(m.start(), len(m.group(1)), m.group(2).strip())
                for m in _HEADING_RE.finditer(body)]

    if not headings:
        # No headings — treat entire body as one section
        text = body.strip()
        if text:
            return [SourceSection(
                source=source,
                doc_title=doc_title,
                unit_type="paragraph",
                unit_range="",
                heading_path=[],
                text=text,
                metadata={
                    "file_type": "md",
                    "tags": tags,
                    "course": course,
                },
            )]
        return []

    sections: list[SourceSection] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title)

    for i, (pos, level, title) in enumerate(headings):
        # Update heading stack
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))

        # Get section text (from this heading to next heading of same or higher level)
        end_pos = headings[i + 1][0] if i + 1 < len(headings) else len(body)
        section_text = body[pos:end_pos].strip()

        # Remove the heading line itself from the text
        first_newline = section_text.find("\n")
        if first_newline > 0:
            section_text = section_text[first_newline:].strip()

        if not section_text:
            continue

        heading_path = [h[1] for h in heading_stack]

        sections.append(SourceSection(
            source=source,
            doc_title=doc_title,
            unit_type="heading",
            unit_range="",
            heading_path=heading_path,
            text=section_text,
            metadata={
                "file_type": "md",
                "heading_level": level,
                "tags": tags,
                "course": course,
            },
        ))

    return sections


def parse_txt(path: str | Path, base_dir: str | Path = ".") -> list[SourceSection]:
    """Parse a plain text file into paragraph-based SourceSections."""
    path = Path(path)
    base_dir = Path(base_dir)

    try:
        relative = path.relative_to(base_dir)
    except ValueError:
        relative = path

    source = str(relative).replace("\\", "/")
    doc_title = path.stem

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="utf-8", errors="replace")

    # Split on double newlines (paragraph boundaries)
    paragraphs = re.split(r"\n\s*\n", content)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    # Group paragraphs into sections (roughly 2-4 paragraphs each)
    sections: list[SourceSection] = []
    buffer = []
    for para in paragraphs:
        buffer.append(para)
        if len("\n\n".join(buffer)) >= 800:
            sections.append(SourceSection(
                source=source,
                doc_title=doc_title,
                unit_type="paragraph",
                unit_range="",
                heading_path=[],
                text="\n\n".join(buffer),
                metadata={"file_type": "txt"},
            ))
            buffer = []

    if buffer:
        sections.append(SourceSection(
            source=source,
            doc_title=doc_title,
            unit_type="paragraph",
            unit_range="",
            heading_path=[],
            text="\n\n".join(buffer),
            metadata={"file_type": "txt"},
        ))

    return sections
