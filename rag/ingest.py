import hashlib
import os
from dataclasses import dataclass, field

from obsidian.parser import parse_markdown_note, split_frontmatter


SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", ".knowledge"}


@dataclass
class SourceDocument:
    """A parsed document that can be chunked for RAG indexing."""

    path: str
    source: str
    text: str
    content_hash: str
    metadata: dict = field(default_factory=dict)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_text_file(path: str) -> tuple[str, str]:
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8-sig")
    return text, _hash_bytes(raw)


def _read_pdf(path: str) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF import requires pypdf. Install requirements.txt first.") from exc

    with open(path, "rb") as f:
        raw = f.read()
        f.seek(0)
        reader = PdfReader(f)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
    return "\n\n".join(pages).strip(), _hash_bytes(raw)


def load_document(path: str, base_dir: str) -> SourceDocument:
    """Load Markdown, text, or PDF into normalized plain text."""
    ext = os.path.splitext(path)[1].lower()
    rel_path = os.path.relpath(path, base_dir).replace(os.sep, "/")

    if ext == ".pdf":
        text, digest = _read_pdf(path)
        metadata = {"kind": "course_document", "source_type": "pdf", "title": os.path.splitext(os.path.basename(path))[0]}
    elif ext == ".md":
        content, digest = _read_text_file(path)
        note = parse_markdown_note(content, rel_path)
        metadata = {
            "kind": "course_document",
            "source_type": "markdown",
            "title": note.title,
            "course": note.course,
            "chapter": note.chapter,
            "tags": note.tags,
        }
        text = note.body
    elif ext == ".txt":
        content, digest = _read_text_file(path)
        _, text = split_frontmatter(content)
        metadata = {"kind": "course_document", "source_type": "text", "title": os.path.splitext(os.path.basename(path))[0]}
    else:
        raise ValueError(f"Unsupported document type: {ext}")

    return SourceDocument(path=path, source=rel_path, text=text, content_hash=digest, metadata=metadata)


def iter_documents(root_dir: str) -> list[SourceDocument]:
    """Load supported documents from a directory tree."""
    root_dir = os.path.abspath(root_dir)
    documents = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".")]
        for filename in files:
            path = os.path.join(root, filename)
            if os.path.splitext(filename)[1].lower() not in SUPPORTED_EXTENSIONS:
                continue
            documents.append(load_document(path, root_dir))
    return sorted(documents, key=lambda item: item.source.casefold())
