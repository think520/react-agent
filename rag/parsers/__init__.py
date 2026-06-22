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


def parse_document(path: str | Path, base_dir: str | Path = ".") -> list[SourceSection]:
    """Parse a document into SourceSection objects.

    Dispatches to the appropriate parser based on file extension.
    Returns empty list if the file type is unsupported or parsing fails.
    """
    path = Path(path)
    ext = path.suffix.lower()

    if ext not in _PARSERS:
        return []

    try:
        import importlib
        mod = importlib.import_module(_PARSERS[ext])
        return mod.parse(path, base_dir)
    except Exception:
        # Parsing failure → empty sections (caller should log)
        return []


SUPPORTED_EXTENSIONS = set(_PARSERS.keys())
