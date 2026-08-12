"""Tests for rag.chunker_v2 — heading-aware adaptive chunking."""

import json
import pytest

from rag.source_section import SourceSection
from rag.chunker_v2 import (
    chunk_sections,
    ChunkingConfig,
    _split_section,
    _merge_short_chunks,
    _build_embedding_text,
    _make_chunk_id,
)


def _make_section(text, heading_path=None, source="test.md", **meta):
    """Helper to create a SourceSection."""
    return SourceSection(
        source=source,
        doc_title="Test Doc",
        unit_type="heading",
        unit_range="",
        heading_path=heading_path or [],
        text=text,
        metadata=meta,
    )


# ── Basic Chunking ─────────────────────────────────────────────────────

class TestBasicChunking:
    def test_single_short_section(self):
        sections = [_make_section("Short text.", heading_path=["Chapter 1"])]
        chunks = chunk_sections(sections)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Short text."
        assert json.loads(chunks[0]["heading_path_json"]) == ["Chapter 1"]
        assert chunks[0]["heading_text"] == "Chapter 1"

    def test_empty_section(self):
        sections = [_make_section("")]
        chunks = chunk_sections(sections)
        assert len(chunks) == 0

    def test_multiple_sections(self):
        # Use config with low min_chars to avoid merging short sections
        cfg = ChunkingConfig(min_chars=10)
        sections = [
            _make_section("Section one content.", heading_path=["A"]),
            _make_section("Section two content.", heading_path=["B"]),
        ]
        chunks = chunk_sections(sections, cfg)
        assert len(chunks) == 2
        assert json.loads(chunks[0]["heading_path_json"]) == ["A"]
        assert json.loads(chunks[1]["heading_path_json"]) == ["B"]


# ── Long Section Split ─────────────────────────────────────────────────

class TestLongSectionSplit:
    def test_long_section_splits(self):
        cfg = ChunkingConfig(target_chars=200, max_chars=300, min_chars=50)
        # Create a section that exceeds max_chars
        paragraphs = [f"Paragraph {i}. " * 20 for i in range(10)]
        text = "\n\n".join(paragraphs)
        sections = [_make_section(text, heading_path=["Chapter"])]
        chunks = chunk_sections(sections, cfg)
        assert len(chunks) > 1
        # All chunks should have the same heading_path
        for c in chunks:
            assert json.loads(c["heading_path_json"]) == ["Chapter"]

    def test_short_section_single_chunk(self):
        cfg = ChunkingConfig(target_chars=2000, max_chars=3000)
        sections = [_make_section("Just a short paragraph.", heading_path=["A"])]
        chunks = chunk_sections(sections, cfg)
        assert len(chunks) == 1


# ── Short Section Merge ────────────────────────────────────────────────

class TestShortMerge:
    def test_merge_short_chunks(self):
        cfg = ChunkingConfig(min_chars=100, target_chars=200, max_chars=300)
        # Two short sections with same heading
        sections = [
            _make_section("Short A.", heading_path=["Same"]),
            _make_section("Short B.", heading_path=["Same"]),
        ]
        chunks = chunk_sections(sections, cfg)
        # They should be merged into one chunk
        assert len(chunks) == 1
        assert "Short A." in chunks[0]["text"]
        assert "Short B." in chunks[0]["text"]

    def test_no_merge_different_headings(self):
        cfg = ChunkingConfig(min_chars=100, target_chars=200, max_chars=300)
        sections = [
            _make_section("Short A.", heading_path=["A"]),
            _make_section("Short B.", heading_path=["B"]),
        ]
        chunks = chunk_sections(sections, cfg)
        assert len(chunks) == 2


# ── Heading Path ───────────────────────────────────────────────────────

class TestHeadingPath:
    def test_heading_path_preserved(self):
        sections = [_make_section("Content", heading_path=["A", "B", "C"])]
        chunks = chunk_sections(sections)
        assert json.loads(chunks[0]["heading_path_json"]) == ["A", "B", "C"]
        assert chunks[0]["heading_text"] == "A > B > C"

    def test_empty_heading_path(self):
        sections = [_make_section("Content")]
        chunks = chunk_sections(sections)
        assert json.loads(chunks[0]["heading_path_json"]) == []
        assert chunks[0]["heading_text"] == ""


# ── Embedding Text ─────────────────────────────────────────────────────

class TestEmbeddingText:
    def test_embedding_text_includes_heading(self):
        sections = [_make_section(
            "ReLU is an activation function.",
            heading_path=["Deep Learning", "Activation Functions"],
        )]
        chunks = chunk_sections(sections)
        emb = chunks[0]["embedding_text"]
        assert "Deep Learning" in emb
        assert "Activation Functions" in emb
        assert "ReLU is an activation function." in emb

    def test_embedding_text_includes_doc_title(self):
        sections = [_make_section("Content")]
        chunks = chunk_sections(sections)
        assert "Test Doc" in chunks[0]["embedding_text"]


# ── Chunk ID ───────────────────────────────────────────────────────────

class TestChunkId:
    def test_deterministic(self):
        id1 = _make_chunk_id("test.md", 0, "hello")
        id2 = _make_chunk_id("test.md", 0, "hello")
        assert id1 == id2

    def test_different_text_different_id(self):
        id1 = _make_chunk_id("test.md", 0, "hello")
        id2 = _make_chunk_id("test.md", 0, "world")
        assert id1 != id2

    def test_different_source_different_id(self):
        id1 = _make_chunk_id("a.md", 0, "hello")
        id2 = _make_chunk_id("b.md", 0, "hello")
        assert id1 != id2


# ── Metadata ───────────────────────────────────────────────────────────

class TestMetadata:
    def test_page_metadata_preserved(self):
        section = _make_section(
            "PDF content", page_start=5, page_end=7, file_type="pdf"
        )
        chunks = chunk_sections([section])
        meta = json.loads(chunks[0]["metadata_json"])
        assert meta["page_start"] == 5
        assert meta["page_end"] == 7
        assert meta["file_type"] == "pdf"

    def test_slide_metadata_preserved(self):
        section = _make_section(
            "PPT content", slide_start=1, slide_end=3, file_type="pptx"
        )
        chunks = chunk_sections([section])
        meta = json.loads(chunks[0]["metadata_json"])
        assert meta["slide_start"] == 1
        assert meta["file_type"] == "pptx"


# ── Section ID ─────────────────────────────────────────────────────────

class TestSectionId:
    def test_section_id_from_heading(self):
        sections = [_make_section("X", heading_path=["Deep Learning", "ReLU"])]
        chunks = chunk_sections(sections)
        assert chunks[0]["section_id"] == "deep-learning/relu"

    def test_section_id_no_heading(self):
        sections = [_make_section("X", source="test.md")]
        chunks = chunk_sections(sections)
        assert "test" in chunks[0]["section_id"]


# ── 2026-08-12: sentence-boundary soft cut ──────────────────────────────

class TestSentenceSoftCut:
    def _chunk(self, text, heading=None):
        from rag.source_section import SourceSection
        sec = SourceSection(
            source="t.md", doc_title="t", unit_type="paragraph", unit_range="",
            heading_path=[heading] if heading else [],
            text=text, metadata={"file_type": "md"},
        )
        cfg = ChunkingConfig(target_chars=1800, max_chars=2600, overlap_chars=350, min_chars=400)
        return chunk_sections([sec], cfg)

    def test_comma_heavy_chinese_cuts_at_punctuation(self):
        # 逗号密集、无句号的长段落：切点必须落在标点后，不能腰斩句子。
        long_text = "，".join(["这是一个非常长的中文句子用来测试切片边界" * 40] * 8)
        chunks = self._chunk(long_text)
        assert len(chunks) >= 2
        boundary_chars = "。，；!！?？."
        for chunk in chunks[:-1]:  # 最后一个 chunk 到文末，允许任意结尾
            assert chunk["text"][-1] in boundary_chars, chunk["text"][-6:]

    def test_strong_punctuation_preferred_over_comma(self):
        # 总长超过 max_chars 触发 hard split；2600 前存在可选句号
        # （"结尾。"）时，切点必须是句号而不是更近的逗号。
        text = ("第一段内容，用逗号连接。" + "第二句很长" * 400 + "，结尾。" + "第三段" * 500)
        chunks = self._chunk(text)
        first = chunks[0]["text"]
        assert first[-1] in "。.!！?？"

    def test_no_punctuation_still_hard_cuts_with_progress(self):
        text = "x" * 3000  # 代码/公式类无标点文本
        chunks = self._chunk(text)
        assert len(chunks) >= 2
        assert sum(len(c["text"]) for c in chunks) >= 3000
