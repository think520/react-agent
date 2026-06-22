"""Tests for rag/parsers — multi-format document parsing."""

import pytest
from pathlib import Path

from rag.source_section import SourceSection
from rag.parsers.markdown_parser import parse as parse_md, _split_markdown


# ── Markdown Parser ─────────────────────────────────────────────────────

class TestMarkdownParser:
    def _write_md(self, tmp_path, name, content):
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_simple_headings(self, tmp_path):
        md = self._write_md(tmp_path, "test.md", """---
title: Test Doc
course: ml
---

# Chapter 1

Introduction text.

## Section 1.1

Details about section 1.1.

## Section 1.2

Details about section 1.2.
""")
        sections = parse_md(md, tmp_path)
        assert len(sections) == 3
        assert sections[0].heading_path == ["Chapter 1"]
        assert sections[1].heading_path == ["Chapter 1", "Section 1.1"]
        assert sections[2].heading_path == ["Chapter 1", "Section 1.2"]
        assert sections[0].doc_title == "Test Doc"
        assert sections[0].metadata.get("course") == "ml"

    def test_nested_headings(self, tmp_path):
        md = self._write_md(tmp_path, "nested.md", """# A

text a

## B

text b

### C

text c

## D

text d
""")
        sections = parse_md(md, tmp_path)
        assert len(sections) == 4
        assert sections[0].heading_path == ["A"]
        assert sections[1].heading_path == ["A", "B"]
        assert sections[2].heading_path == ["A", "B", "C"]
        assert sections[3].heading_path == ["A", "D"]

    def test_no_headings(self, tmp_path):
        md = self._write_md(tmp_path, "flat.md", """Just some text
without any headings.
""")
        sections = parse_md(md, tmp_path)
        assert len(sections) == 1
        assert sections[0].heading_path == []
        assert "without any headings" in sections[0].text

    def test_empty_file(self, tmp_path):
        md = self._write_md(tmp_path, "empty.md", "")
        sections = parse_md(md, tmp_path)
        assert len(sections) == 0

    def test_source_path(self, tmp_path):
        subdir = tmp_path / "course" / "ml"
        subdir.mkdir(parents=True)
        md = subdir / "ch01.md"
        md.write_text("# Title\n\nBody", encoding="utf-8")
        sections = parse_md(md, tmp_path)
        assert sections[0].source == "course/ml/ch01.md"

    def test_file_type_metadata(self, tmp_path):
        md = self._write_md(tmp_path, "test.md", "# H1\n\nContent")
        sections = parse_md(md, tmp_path)
        assert sections[0].metadata["file_type"] == "md"

    def test_frontmatter_tags(self, tmp_path):
        md = self._write_md(tmp_path, "tagged.md", """---
tags: [neural, deep-learning]
---

# Intro

Body text.
""")
        sections = parse_md(md, tmp_path)
        assert "neural" in sections[0].metadata.get("tags", [])


# ── SourceSection ───────────────────────────────────────────────────────

class TestSourceSection:
    def test_creation(self):
        s = SourceSection(
            source="test.md",
            doc_title="Test",
            unit_type="heading",
            unit_range="",
            heading_path=["A", "B"],
            text="Hello",
        )
        assert s.source == "test.md"
        assert s.heading_path == ["A", "B"]

    def test_default_metadata(self):
        s = SourceSection(
            source="x.md",
            doc_title="X",
            unit_type="page",
            unit_range="p1",
        )
        assert s.metadata == {}
        assert s.text == ""
