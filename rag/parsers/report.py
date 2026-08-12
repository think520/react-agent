"""Document extraction report — visible evidence of what a parser produced.

Every document that enters the RAG index carries one extraction report so the
Library can show "this PDF has 3 scanned pages" instead of silently dropping
content. The report is the single source of truth for P5G.0 extraction status;
it lives in SQLite alongside the document record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from rag.source_section import SourceSection

ExtractionStatus = Literal["complete", "partial", "empty", "error"]


@dataclass
class ExtractionReport:
    """Parsed-output summary for one document.

    ``total_units`` counts the structural units the format defines:
    pages for PDF, slides for PPTX, heading/paragraph groups for DOCX / MD / TXT.
    ``extracted_units`` counts units that actually yielded text.
    """

    file_type: str
    parser: str
    status: ExtractionStatus
    total_units: int = 0
    extracted_units: int = 0
    empty_units: int = 0
    extracted_characters: int = 0
    image_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_type": self.file_type,
            "parser": self.parser,
            "status": self.status,
            "total_units": self.total_units,
            "extracted_units": self.extracted_units,
            "empty_units": self.empty_units,
            "extracted_characters": self.extracted_characters,
            "image_count": self.image_count,
            "warnings": list(self.warnings),
        }


def unit_kind_for(file_type: str) -> str:
    """Structural unit label per format (used for counts and messages)."""
    return {
        "pdf": "page",
        "pptx": "slide",
        "docx": "heading section",
        "md": "section",
        "txt": "paragraph group",
    }.get(file_type, "unit")


def build_report(
    file_type: str,
    parser: str,
    sections: list[SourceSection],
    *,
    image_count: int = 0,
    error: str | None = None,
) -> ExtractionReport:
    """Derive an extraction report from parsed sections.

    ``error`` is set when the parser raised before producing sections; the
    report then carries status ``error`` and a ``parser_error`` warning.
    """
    if error is not None:
        return ExtractionReport(
            file_type=file_type,
            parser=parser,
            status="error",
            warnings=["parser_error"],
        )

    unit_key = unit_kind_for(file_type)
    total_units = 0
    extracted_units = 0
    chars = 0
    reported_images = 0
    warnings: list[str] = []
    scanned_pages = 0
    slides_without_text = 0

    for section in sections:
        total_units += 1
        text = section.text or ""
        if text.strip():
            extracted_units += 1
            chars += len(text)
        reported_images += int(section.metadata.get("image_count") or 0)
        if unit_key == "page" and section.metadata.get("needs_ocr"):
            scanned_pages += 1
        if unit_key == "slide":
            # Slide-level emptiness, not merged-section emptiness: a picture
            # slide grouped with text slides must still warn. Real pptx
            # sections carry empty_slides; synthetic sections fall back to
            # whole-section text.
            slides_without_text += int(
                section.metadata.get("empty_slides")
                or (0 if text.strip() else 1)
            )

    if scanned_pages:
        warnings.append("scanned_or_empty_pages")
    if slides_without_text:
        warnings.append("slides_without_text")
    if image_count and not chars:
        warnings.append("images_not_recognized")
    if not chars:
        warnings.append("no_searchable_text")

    if total_units == 0 or extracted_units == 0:
        # Nothing searchable was extracted: an image-only PDF or a deck of
        # slides with no text is "empty", not a partial failure.
        status: ExtractionStatus = "empty"
    elif extracted_units == total_units:
        status = "complete"
    else:
        status = "partial"

    return ExtractionReport(
        file_type=file_type,
        parser=parser,
        status=status,
        total_units=total_units,
        extracted_units=extracted_units,
        empty_units=total_units - extracted_units,
        extracted_characters=chars,
        image_count=reported_images if sections else image_count,
        warnings=sorted(set(warnings)),
    )


def error_report(file_type: str, parser: str) -> ExtractionReport:
    return ExtractionReport(
        file_type=file_type,
        parser=parser,
        status="error",
        warnings=["parser_error"],
    )
