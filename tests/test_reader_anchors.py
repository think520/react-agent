"""W1 E7：划线最小闭环的**数据层** —— chunk 级锚点 + 重锚定。

核对结论：references 早就有 «chunk_id» 字段、E17③ 也有重映射迁移，但**没有任何代码写过它**；
而且 «_public_section» 把 «char_start/char_end» 丢掉了，阅读器拿不到偏移。
（笔记里的托管区块语法是另一半，本轮未做 —— 三家参考项目都没有等价机制，要自定。）
"""

from __future__ import annotations

from memory.anchors import ANCHOR_STALE, resolve_anchor
from memory.personal_store import PersonalKnowledgeStore


TEXT = "Dijkstra 算法每次选择当前距离最小的未访问节点，因此属于贪心策略。"


def test_public_section_keeps_the_char_offsets():
    """① 阅读器要能拿到分段内的字符偏移，否则划线只能存 quote（重锚定会弱很多）。"""
    from service.kb_service import KBService

    public = KBService._public_section({
        "id": "c1", "text": TEXT, "heading_text": "最短路",
        "char_start": 12, "char_end": 24,
    })

    assert public["char_start"] == 12, public
    assert public["char_end"] == 24, public


def test_public_section_tolerates_missing_offsets():
    from service.kb_service import KBService

    public = KBService._public_section({"id": "c1", "text": TEXT})

    assert public["char_start"] is None and public["char_end"] is None


def test_resolve_anchor_is_exact_when_offsets_still_match():
    anchor = {"quote": "贪心策略", "char_start": TEXT.index("贪心策略"), "char_end": TEXT.index("贪心策略") + 4}

    resolved = resolve_anchor(anchor, TEXT)

    assert resolved["status"] == "exact", resolved
    assert TEXT[resolved["char_start"]:resolved["char_end"]] == "贪心策略"


def test_resolve_anchor_relocates_when_the_text_moved():
    """分段重切/编辑后偏移会变 —— 靠 quote 找回来，并如实说这是"重新定位"。"""
    anchor = {"quote": "贪心策略", "char_start": 0, "char_end": 4}

    resolved = resolve_anchor(anchor, TEXT)

    assert resolved["status"] == "relocated", resolved
    assert TEXT[resolved["char_start"]:resolved["char_end"]] == "贪心策略"


def test_resolve_anchor_reports_stale_instead_of_guessing():
    anchor = {"quote": "这段文字已经不在分段里了", "char_start": 0, "char_end": 5}

    resolved = resolve_anchor(anchor, TEXT)

    assert resolved["status"] == ANCHOR_STALE, resolved
    assert resolved["char_start"] is None and resolved["char_end"] is None


def test_anchors_round_trip_through_the_store(tmp_path):
    store = PersonalKnowledgeStore(str(tmp_path))
    created = store.add_document_anchor(
        document_id="doc-1", chunk_id="c1", quote="贪心策略",
        char_start=28, char_end=32, note="这是关键假设",
    )

    assert created["anchor_id"], created
    fetched = store.list_document_anchors("doc-1")
    assert [item["quote"] for item in fetched] == ["贪心策略"], fetched
    assert fetched[0]["note"] == "这是关键假设", fetched

    # 另一个文档的锚点不会串进来。
    store.add_document_anchor(document_id="doc-2", chunk_id="c9", quote="别的")
    assert len(store.list_document_anchors("doc-1")) == 1

    assert store.delete_document_anchor(created["anchor_id"]) is True
    assert store.list_document_anchors("doc-1") == []


def _kb_with_chunk(workspace: str, chunk_id: str = "c1", text: str = TEXT) -> None:
    from rag.sqlite_store import KBSQLiteStore, make_chunk_row

    kb = KBSQLiteStore(workspace)
    kb.init_db()
    kb.upsert_document("doc-1", "lesson.md", "hash", title="算法课")
    kb.insert_chunks([make_chunk_row(
        chunk_id, "doc-1", "lesson.md", 0, text,
        title="算法课", char_start=0, char_end=len(text),
    )])
    kb.close()


def test_service_reports_how_well_each_anchor_still_points(tmp_path):
    """列表要说明每条划线的现状：还指得到 / 位置变了 / 已经失效。"""
    from service.anchor_service import AnchorService

    workspace = str(tmp_path)
    _kb_with_chunk(workspace)
    service = AnchorService(workspace)
    good = service.create(document_id="doc-1", chunk_id="c1", quote="贪心策略")
    moved = service.create(document_id="doc-1", chunk_id="c1", quote="贪心策略", char_start=0, char_end=4)
    gone = service.create(document_id="doc-1", chunk_id="c1", quote="这段话已经没了")

    listed = service.list_for_document("doc-1")

    assert listed["ok"] and listed["count"] == 3, listed
    by_id = {item["anchor_id"]: item["resolution"]["status"] for item in listed["anchors"]}
    assert by_id[good["anchor"]["anchor_id"]] == "relocated", by_id
    assert by_id[moved["anchor"]["anchor_id"]] == "relocated", by_id
    assert by_id[gone["anchor"]["anchor_id"]] == "stale", by_id


def test_service_refuses_an_anchor_without_a_quote(tmp_path):
    """没有引文的划线以后无法重新定位 —— 一开始就不收。"""
    from service.anchor_service import AnchorService

    result = AnchorService(str(tmp_path)).create(document_id="doc-1", chunk_id="c1", quote="  ")

    assert result["ok"] is False, result
    assert result["code"] == "empty_quote", result


def test_delete_reports_a_missing_anchor(tmp_path):
    from service.anchor_service import AnchorService

    result = AnchorService(str(tmp_path)).delete("nope")

    assert result["ok"] is False and result["code"] == "anchor_not_found", result
