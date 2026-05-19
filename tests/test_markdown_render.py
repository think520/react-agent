from cli.markdown_render import render_markdown_lines


def test_render_markdown_headings_lists_and_inline_code():
    lines = render_markdown_lines("### 标题\n\n- use `rag_search`\n1. **第一步**")
    output = "\n".join(lines)

    assert "###" not in output
    assert "标题" in output
    assert "-" in output
    assert "rag_search" in output
    assert "第一步" in output


def test_render_markdown_code_fences_without_backticks():
    lines = render_markdown_lines("```python\nprint('hi')\n```")
    output = "\n".join(lines)

    assert "```" not in output
    assert "code: python" in output
    assert "print('hi')" in output


def test_render_markdown_table_skips_separator_row():
    lines = render_markdown_lines("| 工具 | 用途 |\n|---|---|\n| rag_search | 检索 |")
    output = "\n".join(lines)

    assert "---" not in output
    assert "工具" in output
    assert "rag_search" in output
