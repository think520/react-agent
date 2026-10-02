import { describe, expect, it } from "vitest";

import { anchorDraftFromRange, resolveQuoteOffsets } from "./readerAnchors";

/**
 * W1 E7 第二批：把阅读器里的选区变成**锚点**（四元组 + 引文）。
 *
 * 关键取舍：DOM 里的文字是**渲染后**的（markdown 的 ** 与 # 都没了），
 * 而分段文本是原文 —— 偏移只能在原文里找得到才算数，找不到就如实存 null，
 * 不编一个会在重锚定时立刻失效的偏移。
 */

const SECTION_TEXT = "Dijkstra 算法每次选择**当前距离最小**的未访问节点，因此属于贪心策略。";

describe("resolveQuoteOffsets", () => {
  it("finds the offsets of an exact quote in the section text", () => {
    const offsets = resolveQuoteOffsets(SECTION_TEXT, "因此属于贪心策略");

    expect(offsets).not.toBeNull();
    expect(SECTION_TEXT.slice(offsets!.char_start, offsets!.char_end)).toBe("因此属于贪心策略");
  });

  it("returns null when the quote is not in the raw text", () => {
    // 渲染后的文字丢了 markdown 记号 → 原文里搜不到，如实返回 null。
    expect(resolveQuoteOffsets(SECTION_TEXT, "Dijkstra 算法每次选择当前距离最小的未访问节点")).toBeNull();
  });

  it("does not invent offsets when whitespace really differs", () => {
    const text = "第一行\n\n第二行：结论是贪心。";
    // 渲染把换行压成了一个空格：偏移在原文里不再可靠 → 如实返回 null。
    // 引文本身仍然会被存下来，以后可以靠它重新定位。
    expect(resolveQuoteOffsets(text, "第一行 第二行：结论是贪心。")).toBeNull();
  });

  it("tolerates extra whitespace when the lengths still line up", () => {
    const text = "结论：a b 而已。";
    const offsets = resolveQuoteOffsets(text, "结论：a  b 而已。");

    expect(offsets).not.toBeNull();
    expect(text.slice(offsets!.char_start, offsets!.char_end)).toContain("a b");
  });

  it("ignores empty quotes", () => {
    expect(resolveQuoteOffsets(SECTION_TEXT, "   ")).toBeNull();
  });
});

describe("anchorDraftFromRange", () => {
  function rangeOver(html: string, chunkId: string, pick: (root: HTMLElement) => [Node, number, Node, number]) {
    document.body.innerHTML = `<section data-chunk-id="${chunkId}"><div class="prose">${html}</div></section>`;
    const root = document.querySelector<HTMLElement>(".prose")!;
    const [startNode, startOffset, endNode, endOffset] = pick(root);
    const range = document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    return range;
  }

  it("reads the chunk id and the quote from the selection", () => {
    const range = rangeOver("贪心策略就在这里。", "c1", (root) => {
      const text = root.firstChild as Text;
      return [text, 0, text, 4];
    });

    const draft = anchorDraftFromRange(range, [{ chunk_id: "c1", text: "贪心策略就在这里。" }]);

    expect(draft).not.toBeNull();
    expect(draft!.chunk_id).toBe("c1");
    expect(draft!.quote).toBe("贪心策略");
    expect(draft!.char_start).toBe(0);
    expect(draft!.char_end).toBe(4);
  });

  it("keeps the quote but reports no offsets when the raw text differs", () => {
    const range = rangeOver("贪心策略就在这里。", "c1", (root) => {
      const text = root.firstChild as Text;
      return [text, 0, text, 4];
    });

    const draft = anchorDraftFromRange(range, [{ chunk_id: "c1", text: "**贪心**策略就在这里。" }]);

    expect(draft!.quote).toBe("贪心策略");
    expect(draft!.char_start).toBeNull();
    expect(draft!.char_end).toBeNull();
  });

  it("returns null outside any section (选区不在分段里)", () => {
    document.body.innerHTML = "<p>游离的段落</p>";
    const text = document.querySelector("p")!.firstChild as Text;
    const range = document.createRange();
    range.setStart(text, 0);
    range.setEnd(text, 2);

    expect(anchorDraftFromRange(range, [])).toBeNull();
  });
});
