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

    # Extract sections by heading style, walking the body **in order** so a
    # table stays inside the section it belongs to.
    from docx.table import Table

    sections: list[SourceSection] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    current_text: list[str] = []
    current_heading_path: list[str] = []
    current_image_count = 0
    current_table_count = 0

    def _flush():
        nonlocal current_text, current_image_count, current_table_count
        text = "\n".join(current_text).strip()
        if text or current_image_count:
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
                    "image_count": current_image_count,
                    "table_count": current_table_count,
                },
            ))
        current_text = []
        current_image_count = 0
        current_table_count = 0

    for block in _iter_blocks(doc):
        if isinstance(block, Table):
            # python-docx keeps cell text out of doc.paragraphs, so tables used
            # to be dropped silently: unsearchable and unusable as evidence.
            table_text = _table_text(block)
            if table_text:
                current_text.append(table_text)
                current_table_count += 1
            continue

        para = block
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
            # Count embedded pictures in this paragraph (P5G.0: an
            # image-heavy DOCX must be reported, not silently flattened).
            current_image_count += _para_image_count(para)
            text = para.text.strip()
            if text:
                current_text.append(text)

    _flush()
    return sections


def _iter_blocks(doc):
    """Yield paragraphs and tables in document order.

    `doc.paragraphs` and `doc.tables` are separate lists, so their relative
    position is lost; walking the body children restores it.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


def _table_text(table) -> str:
    """Render a table as one pipe-separated line per row."""
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _para_image_count(paragraph) -> int:
    """Count images inside one paragraph (inline drawings / legacy pict)."""
    try:
        from docx.oxml.ns import qn
        element = paragraph._element
        drawings = element.findall(".//" + qn("w:drawing"))
        picts = element.findall(".//" + qn("w:pict"))
        return len(drawings) + len(picts)
    except Exception:
        return 0


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
