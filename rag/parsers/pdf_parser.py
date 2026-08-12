"""PDF parser — page-aware section splitting.

Uses pypdf (MIT/BSD licensed) for text extraction.
Detects scanned pages (empty text) and marks them needs_ocr.
"""

from __future__ import annotations

from pathlib import Path

from rag.source_section import SourceSection


def parse(path: str | Path, base_dir: str | Path = ".") -> list[SourceSection]:
    """Parse a PDF file into page-aware SourceSections."""
    path = Path(path)
    base_dir = Path(base_dir)

    try:
        relative = path.relative_to(base_dir)
    except ValueError:
        relative = path

    source = str(relative).replace("\\", "/")
    doc_title = path.stem

    try:
        from pypdf import PdfReader
    except ImportError:
        return []

    # pypdf logs and returns an empty reader instead of raising on garbage
    # input; treat files that are not actually PDFs as parse failures.
    try:
        with open(path, "rb") as handle:
            header = handle.read(5)
    except OSError:
        return []
    if header != b"%PDF-":
        raise ValueError(f"not a PDF file: {path.name}")

    try:
        reader = PdfReader(str(path))
    except Exception:
        return []

    sections: list[SourceSection] = []
    for i, page in enumerate(reader.pages):
        text = ""
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()

        if not text:
            # Scanned or image-only page — mark for OCR
            sections.append(SourceSection(
                source=source,
                doc_title=doc_title,
                unit_type="page",
                unit_range=f"p{i + 1}",
                heading_path=[],
                text="",
                metadata={
                    "file_type": "pdf",
                    "page_start": i + 1,
                    "page_end": i + 1,
                    "needs_ocr": True,
                },
            ))
            continue

        # Try to detect heading from first line
        lines = text.split("\n")
        heading_path = []
        first_line = lines[0].strip() if lines else ""

        # Heuristic: if first line is short and looks like a heading
        if first_line and len(first_line) < 100 and not first_line.endswith(("。", ".", "，", ",")):
            # Check if it looks like a chapter/section title
            if any(first_line.startswith(prefix) for prefix in
                   ("第", "Chapter", "CHAPTER", "Ch.", "§", "Section")):
                heading_path = [first_line]

        sections.append(SourceSection(
            source=source,
            doc_title=doc_title,
            unit_type="page",
            unit_range=f"p{i + 1}",
            heading_path=heading_path,
            text=text,
            metadata={
                "file_type": "pdf",
                "page_start": i + 1,
                "page_end": i + 1,
            },
        ))

    # Merge consecutive pages with the same heading into larger sections
    return _merge_pages(sections)


def _merge_pages(sections: list[SourceSection], max_pages: int = 3) -> list[SourceSection]:
    """Merge consecutive pages into larger sections for better chunk context."""
    if not sections:
        return []

    merged: list[SourceSection] = []
    buffer: list[SourceSection] = [sections[0]]

    for section in sections[1:]:
        # Merge if: same heading, no OCR needed, and buffer not too large
        same_heading = section.heading_path == buffer[-1].heading_path
        no_ocr = not section.metadata.get("needs_ocr") and not buffer[-1].metadata.get("needs_ocr")
        not_full = len(buffer) < max_pages

        if same_heading and no_ocr and not_full:
            buffer.append(section)
        else:
            merged.append(_combine_pages(buffer))
            buffer = [section]

    if buffer:
        merged.append(_combine_pages(buffer))

    return merged


def _combine_pages(pages: list[SourceSection]) -> SourceSection:
    """Combine multiple page sections into one."""
    if len(pages) == 1:
        return pages[0]

    first = pages[0]
    last = pages[-1]
    combined_text = "\n\n".join(p.text for p in pages if p.text)

    return SourceSection(
        source=first.source,
        doc_title=first.doc_title,
        unit_type="page",
        unit_range=f"p{first.metadata.get('page_start', 1)}-p{last.metadata.get('page_end', 1)}",
        heading_path=first.heading_path,
        text=combined_text,
        metadata={
            "file_type": "pdf",
            "page_start": first.metadata.get("page_start"),
            "page_end": last.metadata.get("page_end"),
        },
    )
