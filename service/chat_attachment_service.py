"""Extract text from ad-hoc files attached directly in a chat turn.

Files attached in the chat composer are scoped to that turn (they are NOT
silently copied into the user's library folder, preserving the library boundary).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from rag.parsers import SUPPORTED_EXTENSIONS as PARSER_EXTENSIONS
from rag.parsers import parse_document
from service._result import err as _err
from service._result import ok as _ok

MAX_CHAT_FILE_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 24_000

_PLAIN_TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".html", ".htm", ".css", ".scss", ".less", ".svg", ".xml",
    ".sql", ".sh", ".bash", ".zsh", ".bat", ".ps1",
    ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs",
    ".go", ".rs", ".rb", ".php", ".swift", ".r", ".tex", ".log",
})


def _decode_plain_text(raw: bytes) -> str | None:
    if b"\x00" in raw[:4096]:
        return None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def extract_chat_file(
    filename: str,
    content: bytes,
    mime_type: str = "",
) -> dict[str, Any]:
    """Extract readable text from an uploaded chat attachment without touching the library."""
    safe_name = os.path.basename((filename or "").strip())
    if not safe_name:
        return _err("文件名不能为空。", code="invalid_attachment")
    if not content:
        return _err(f"「{safe_name}」是空文件，无法读取内容。", code="empty_attachment")
    if len(content) > MAX_CHAT_FILE_BYTES:
        return _err(
            f"「{safe_name}」超过 10 MB 聊天附件上限；大文档建议先导入资料库再提问。",
            code="attachment_too_large",
        )

    ext = Path(safe_name).suffix.lower()
    extracted = ""

    if ext in PARSER_EXTENSIONS and ext not in {".md", ".txt"}:
        with tempfile.TemporaryDirectory(prefix="bobodan_chat_att_") as tmp_dir:
            tmp_path = Path(tmp_dir) / safe_name
            tmp_path.write_bytes(content)
            sections, report = parse_document(tmp_path, tmp_dir)
            parts: list[str] = []
            for section in sections:
                text = (section.text or "").strip()
                if not text:
                    continue
                if section.heading:
                    parts.append(f"## {section.heading}\n{text}")
                else:
                    parts.append(text)
            extracted = "\n\n".join(parts).strip()
            if not extracted:
                hint = "可能是扫描件或空白文档，暂无可提取文字。" if report.status != "error" else "文档解析失败。"
                return _err(f"无法从「{safe_name}」提取正文：{hint}", code="attachment_extract_empty")
    elif ext in _PLAIN_TEXT_EXTENSIONS or (mime_type or "").startswith("text/"):
        decoded = _decode_plain_text(content)
        if decoded is None or not decoded.strip():
            return _err(f"「{safe_name}」不包含可读取的纯文本内容。", code="attachment_extract_empty")
        extracted = decoded.strip()
    else:
        return _err(
            f"暂不支持直接读取「{safe_name}」（支持图片、PDF、Word、PPT、Markdown、文本与常见代码文件）。",
            code="unsupported_attachment_type",
        )

    truncated = len(extracted) > MAX_EXTRACTED_CHARS
    if truncated:
        extracted = extracted[:MAX_EXTRACTED_CHARS]

    return _ok(
        attachment={
            "type": "file",
            "name": safe_name,
            "mime_type": mime_type or "",
            "text": extracted,
            "char_count": len(extracted),
            "truncated": truncated,
        }
    )
