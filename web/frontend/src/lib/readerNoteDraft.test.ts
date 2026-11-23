import { describe, expect, it } from "vitest";

import {
  MAX_NOTE_CONTENT_LENGTH,
  appendHighlightToNoteContent,
  buildHighlightQuoteBlock,
  formatHighlightsSummaryNote,
  formatSingleHighlightNote,
  mergeDocumentReferences,
} from "./readerNoteDraft";

describe("readerNoteDraft", () => {
  it("formats a single highlight blockquote with source heading", () => {
    const note = formatSingleHighlightNote("第一行\n第二行", "图算法讲义", "Dijkstra 算法");
    expect(note.title).toBe("摘录 · 图算法讲义");
    expect(note.content).toContain("> 第一行\n> 第二行");
    expect(note.content).toContain("—— 摘自 《图算法讲义》 · Dijkstra 算法");
  });

  it("formats document highlight summary and respects max length", () => {
    const longQuote = "a".repeat(MAX_NOTE_CONTENT_LENGTH + 400);
    const note = formatHighlightsSummaryNote([{ quote: longQuote }], "长资料");
    expect(note.title).toBe("划线汇总 · 长资料");
    expect(note.content.length).toBeLessThanOrEqual(MAX_NOTE_CONTENT_LENGTH);
  });

  it("appends to existing note cleanly and marks truncation if overflowed", () => {
    const existing = "既有笔记正文。";
    const block = buildHighlightQuoteBlock("关键结论", "导论");
    const appended = appendHighlightToNoteContent(existing, block);
    expect(appended.truncated).toBe(false);
    expect(appended.content).toBe(`既有笔记正文。\n\n${block}`);

    const overflowed = appendHighlightToNoteContent("x".repeat(4995), "新增内容超过上限");
    expect(overflowed.truncated).toBe(true);
    expect(overflowed.content.length).toBeLessThanOrEqual(MAX_NOTE_CONTENT_LENGTH);
  });

  it("deduplicates document references when merging", () => {
    const merged = mergeDocumentReferences(
      [{ document_id: "doc-1", chunk_id: "c1", title: "图算法" }],
      [
        { document_id: "doc-1", chunk_id: "c1", title: "图算法" },
        { document_id: "doc-1", chunk_id: "c2", title: "图算法" },
      ],
    );
    expect(merged).toHaveLength(2);
    expect(merged.map((item) => item.chunk_id)).toEqual(["c1", "c2"]);
  });
});
