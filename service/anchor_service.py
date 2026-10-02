"""划线锚点服务（W1 E7）。

存储与重锚定分别在 «memory/personal_store.py» 与 «memory/anchors.py»；
这一层负责"拿当前索引里的分段文本去核对锚点"，并给出**如实**的状态：
«exact» / «relocated» / «stale»。找不到就说找不到，不假装还指得到。
"""

from __future__ import annotations

import logging
from typing import Any

from memory.anchors import resolve_anchor
from memory.personal_store import PersonalKnowledgeStore
from service._result import err as _err, ok as _ok

logger = logging.getLogger(__name__)


class AnchorService:
    def __init__(self, workspace: str, config: dict | None = None):
        self.workspace = workspace
        self.config = config or {}

    def _chunk_texts(self, chunk_ids: list[str]) -> dict[str, str]:
        if not chunk_ids:
            return {}
        from rag.sqlite_store import KBSQLiteStore

        store = KBSQLiteStore(self.workspace)
        try:
            store.init_db()
            rows = store.get_chunks_by_ids([cid for cid in chunk_ids if cid])
        except Exception as exc:  # pragma: no cover - 依索引实现而定
            logger.warning("Could not load chunks for anchors: %s", exc)
            return {}
        finally:
            store.close()
        return {str(cid): str(row.get("text") or "") for cid, row in (rows or {}).items()}

    def _with_resolution(self, anchors: list[dict]) -> list[dict]:
        texts = self._chunk_texts([str(item.get("chunk_id") or "") for item in anchors])
        resolved: list[dict] = []
        for anchor in anchors:
            chunk_id = str(anchor.get("chunk_id") or "")
            if not chunk_id:
                resolved.append({**anchor, "resolution": {
                    "status": "stale", "char_start": None, "char_end": None,
                }})
                continue
            resolved.append({
                **anchor,
                "resolution": resolve_anchor(anchor, texts.get(chunk_id, "")),
            })
        return resolved

    def create(
        self,
        *,
        document_id: str,
        chunk_id: str = "",
        quote: str,
        char_start: int | None = None,
        char_end: int | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        if not str(document_id).strip():
            return _err("缺少文档 id。", code="document_not_found")
        if not str(quote or "").strip():
            return _err("划线要带上一段原文，否则以后无法重新定位。", code="empty_quote")
        store = PersonalKnowledgeStore(self.workspace)
        anchor = store.add_document_anchor(
            document_id=document_id, chunk_id=chunk_id, quote=quote,
            char_start=char_start, char_end=char_end, note=note,
        )
        return _ok(anchor=self._with_resolution([anchor])[0])

    def list_for_document(self, document_id: str) -> dict[str, Any]:
        store = PersonalKnowledgeStore(self.workspace)
        anchors = store.list_document_anchors(document_id)
        return _ok(anchors=self._with_resolution(anchors), count=len(anchors))

    def delete(self, anchor_id: str) -> dict[str, Any]:
        store = PersonalKnowledgeStore(self.workspace)
        if not store.delete_document_anchor(anchor_id):
            return _err("这条划线已经不存在了。", code="anchor_not_found")
        return _ok(anchor_id=anchor_id)
