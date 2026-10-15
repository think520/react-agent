"""DOCX 表格必须进正文。

`docx_parser` 只遍历 `doc.paragraphs`，而 python-docx 不把表格单元格放进
`paragraphs`——所以表格文字此前**一个字都进不了索引**：既搜不到，也永远
不可能成为概念证据。这个文件盯住的就是这个静默丢失。
"""

from __future__ import annotations

import pytest


def _docx_with_table(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("第一章", level=1)
    document.add_paragraph("正文段落一")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "概念"
    table.cell(0, 1).text = "说明"
    table.cell(1, 0).text = "向量检索"
    table.cell(1, 1).text = "按相似度取最近的片段"
    document.add_paragraph("表格之后的段落")
    path = tmp_path / "with-table.docx"
    document.save(str(path))
    return path


def test_a_docx_table_reaches_the_parsed_text(tmp_path):
    from rag.parsers.docx_parser import parse

    sections = parse(_docx_with_table(tmp_path), tmp_path)
    joined = "\n".join(section.text for section in sections)

    assert "向量检索" in joined, "表格里的字必须进正文，否则检索永远搜不到"
    assert "按相似度取最近的片段" in joined


def test_the_table_stays_inside_its_section(tmp_path):
    from rag.parsers.docx_parser import parse

    sections = parse(_docx_with_table(tmp_path), tmp_path)

    assert sections, "至少应产出一个 section"
    assert "向量检索" in sections[0].text, "表格应留在它所属的小节里，而不是被丢到最后"
    assert any(int(section.metadata.get("table_count") or 0) >= 1 for section in sections)
