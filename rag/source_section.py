"""SourceSection — unified intermediate structure for multi-format parsing.

All file types (Markdown, PDF, PPT, Word, TXT) are first parsed into
SourceSection objects, then passed to the heading-aware chunker.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceSection:
    """A structural unit from a source document.

    For Markdown: one heading + its content.
    For PDF: one page or group of pages.
    For PPT: one slide or group of slides.
    For Word: one heading section.
    For TXT: one paragraph group.
    """

    source: str  # "course/deep-learning/ch03.md"
    doc_title: str  # "神经网络基础"
    unit_type: str  # "heading" | "page" | "slide" | "paragraph"
    unit_range: str  # "p12-p14" | "slide 5-7" | ""
    heading_path: list[str] = field(default_factory=list)  # ["第三章", "激活函数"]
    text: str = ""
    metadata: dict = field(default_factory=dict)
    # metadata keys:
    #   file_type: str — "md" | "pdf" | "docx" | "pptx" | "txt"
    #   page_start: int | None
    #   page_end: int | None
    #   slide_start: int | None
    #   slide_end: int | None
    #   heading_level: int | None
    #   needs_ocr: bool (PDF only)
    #   tags: list[str] (Markdown only)
    #   course: str | None (Markdown only)
