"""FTS5 查询构造：用户输入里的引号/运算符不能让检索**静默变空**。

核对根因：«_build_fts_query» 对 «* ( ) :» 的处理是**在 token 内部插引号**（«a*b» → «a"*"b»），
外层再用引号包一次 → 生成 «"a"*"b"» 这种不合法表达式：FTS5 会把后面的裸 token 当成
**列名**（«no such column: 数学»），或者直接报语法错（«syntax error near "OR"»）。
结果不是"报错退出"，而是**FTS 腿静默返回空** —— 用户看到的是"检索不到"，不是"查询写错了"。
"""

from __future__ import annotations

from rag.sqlite_store import KBSQLiteStore, _build_fts_query, make_chunk_row


def _quoted_atoms(fts_query: str) -> list[str]:
    """把生成式拆成原子，方便断言"每个原子都是被引号包住的字面量"。"""
    return [part.strip() for part in fts_query.split(" OR ") if part.strip()]


def test_a_quoted_phrase_stays_one_quoted_atom():
    fts_query = _build_fts_query('"贪心策略"')

    atoms = _quoted_atoms(fts_query)
    assert atoms, fts_query
    for atom in atoms:
        assert atom.startswith('"') and atom.endswith('"'), (atom, fts_query)


def test_operators_inside_a_token_do_not_break_the_expression():
    """«* ( ) :» 在引号里是**字面量**，不该被拆出去。"""
    fts_query = _build_fts_query("a*b(c):d")

    assert '*' in fts_query and '(' in fts_query
    # 不能出现 «"a"*"b"» 这种把运算符露在引号外的形态。
    assert '"*"' not in fts_query, fts_query
    assert '":"' not in fts_query, fts_query


def test_a_bare_operator_word_is_quoted_too():
    fts_query = _build_fts_query("greedy OR dp")

    atoms = _quoted_atoms(fts_query)
    assert '"or"' in atoms, atoms
    for atom in atoms:
        assert atom.startswith('"') and atom.endswith('"'), atom


def test_punctuation_only_query_yields_nothing_rather_than_a_broken_expression():
    # 纯标点没有词字符 → 必须返回空串（_HAS_WORD_CHAR 过滤），不是残破表达式也不是空引号对。
    assert _build_fts_query("***") == ""
    assert _build_fts_query("   ") == ""


def test_the_generated_query_actually_runs_against_a_real_fts_table(tmp_path):
    """最终判据：生成式喂给真 FTS5 不能报错，而且要真的命中。"""
    store = KBSQLiteStore(str(tmp_path))
    store.init_db()
    try:
        store.upsert_document("doc-1", "greedy.md", "hash", title="贪心策略")
        store.insert_chunks([make_chunk_row(
            "c1", "doc-1", "greedy.md", 0,
            "贪心策略在每一步都选择当前看起来最好的选项。", title="贪心策略",
        )])

        for query in ('"贪心策略"', "贪心 OR 策略", "贪心(策略)", "贪心*策略", "贪心:策略"):
            hits = store.search_fts5(query, top_k=5)
            assert hits, f"查询 {query!r} 应当命中（生成式：{_build_fts_query(query)!r}）"
    finally:
        store.close()


def test_search_never_raises_on_hostile_input(tmp_path):
    store = KBSQLiteStore(str(tmp_path))
    store.init_db()
    try:
        store.upsert_document("doc-1", "greedy.md", "hash", title="贪心")
        store.insert_chunks([make_chunk_row("c1", "doc-1", "greedy.md", 0, "贪心策略。", title="贪心")])

        for query in ['"""', "NEAR(", "a NEAR/3 b", "(", ")", ":", "AND", "NOT"]:
            store.search_fts5(query, top_k=5)  # 不抛就算过
    finally:
        store.close()
