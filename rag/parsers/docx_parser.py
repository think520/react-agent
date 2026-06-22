"""DOCX parser — heading-style-aware section splitting.

Uses python-docx for document parsing.
Reads Heading 1/2/3 styles as section boundaries.
"""

from __future__ import annotations

from pathlib import Path

from rag.source_section import SourceSection


def parse(path: str | Path, base_dir: str | Path = ".") -> list[SourceSection]:
    """Parse a DOCX file into heading-style-aware SourceSections."""
    path = Path(path)
    base_dir = Path(base_dir)

    try:
        relative = path.relative_to(base_dir)
    except ValueError:
        relative = path

    source = str(relative).replace("\\", "/")
    doc_title = path.stem

    try:
        from docx import Document
    except ImportError:
        return []

    try:
        doc = Document(str(path))
    except Exception:
        return []

    # Extract sections by heading style
    sections: list[SourceSection] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    current_text: list[str] = []
    current_heading_path: list[str] = []

    def _flush():
        nonlocal current_text
        text = "\n".join(current_text).strip()
        if text:
            sections.append(SourceSection(
                source=source,
                doc_title=doc_title,
                unit_type="heading",
                unit_range="",
                heading_path=list(current_heading_path),
                text=text,
                metadata={
                    "file_type": "docx",
                    "heading_level": heading_stack[-1][0] if heading_stack else 0,
                },
            ))
        current_text = []

    for para in doc.paragraphs:
        style_name = para.style.name if para.style else ""

        # Detect heading styles
        heading_level = _get_heading_level(style_name)

        if heading_level > 0:
            _flush()
            title = para.text.strip()
            if not title:
                continue

            # Update heading stack
            while heading_stack and heading_stack[-1][0] >= heading_level:
                heading_stack.pop()
            heading_stack.append((heading_level, title))
            current_heading_path = [h[1] for h in heading_stack]
        else:
            text = para.text.strip()
            if text:
                current_text.append(text)

    _flush()
    return sections


def _get_heading_level(style_name: str) -> int:
    """Extract heading level from Word style name.

    Returns 0 if not a heading style.
    """
    style_lower = style_name.lower()

    # Standard heading styles
    for level in range(1, 10):
        if style_lower == f"heading {level}":
            return level

    # Chinese heading styles
    heading_map = {
        "标题 1": 1, "标题 2": 2, "标题 3": 3,
        "标题 4": 4, "标题 5": 5, "标题 6": 6,
    }
    for name, level in heading_map.items():
        if name in style_name:
            return level

    return 0
