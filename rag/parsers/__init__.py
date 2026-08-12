"""Multi-format document parsers.

Each parser converts a file into a list of SourceSection objects.
The chunker_v2 then converts sections into TextChunk objects.
"""

from __future__ import annotations

from pathlib import Path

from rag.source_section import SourceSection

# Supported extensions → parser module
_PARSERS = {
    ".md": "rag.parsers.markdown_parser",
    ".txt": "rag.parsers.markdown_parser",  # TXT uses paragraph fallback
    ".pdf": "rag.parsers.pdf_parser",
    ".docx": "rag.parsers.docx_parser",
    ".pptx": "rag.parsers.pptx_parser",
}


def parse_document(
    path: str | Path, base_dir: str | Path = "."
) -> tuple[list[SourceSection], "ExtractionReport"]:
    """Parse a document into SourceSection objects plus an extraction report.

    Dispatches to the appropriate parser based on file extension. The report
    records what the parser actually produced (P5G.0 extraction status), so
    the caller can distinguish "empty PDF" from "unsupported file" from
    "parser crashed".
    """
    from rag.parsers.report import ExtractionReport, build_report, error_report

    path = Path(path)
    ext = path.suffix.lower()
    file_type = ext.lstrip(".") or "unknown"
    parser_name = _PARSERS.get(ext, "unknown")

    if ext not in _PARSERS:
        return [], ExtractionReport(
            file_type=file_type, parser=parser_name, status="error",
            warnings=["parser_error"],
        )

    try:
        import importlib
        mod = importlib.import_module(_PARSERS[ext])
        sections = mod.parse(path, base_dir)
        return sections, build_report(file_type, parser_name, sections)
    except Exception:
        # Parsing failure → empty sections + error report (caller should log)
        return [], error_report(file_type, parser_name)


SUPPORTED_EXTENSIONS = set(_PARSERS.keys())
