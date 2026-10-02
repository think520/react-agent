import { describe, expect, it } from "vitest";

import { clearHighlights, highlightQuote } from "./domHighlight";

/**
 * W1 E7：把划线画在**正文里**。
 *
 * 关键取舍：正文是 markdown **渲染后**的文字，锚点存的偏移是**原文**偏移 ——
 * 两者对不上（渲染会吃掉 ** 与 #）。所以在 DOM 里按**引文**定位：
 * 引文本来就是从这段正文选出来的，一定能在渲染后的文字里找到。
 */

function mount(html: string): HTMLElement {
  document.body.innerHTML = `<section data-chunk-id="c1"><div class="prose">${html}</div></section>`;
  return document.querySelector<HTMLElement>(".prose")!;
}

describe("highlightQuote", () => {
  it("wraps an exact quote in a mark", () => {
    const root = mount("Dijkstra 属于贪心策略，因为每次选局部最优。");

    const ok = highlightQuote(root, "贪心策略");

    expect(ok).toBe(true);
    const marks = root.querySelectorAll("mark.reader-anchor-mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("贪心策略");
  });

  it("still works when the quote spans inline markup", () => {
    // 渲染后的正文里"贪心策略"被 <strong> 切开 —— 引文跨节点也要能画出来。
    const root = mount("Dijkstra 属于<strong>贪心</strong>策略，因为每次选局部最优。");

    const ok = highlightQuote(root, "贪心策略");

    expect(ok).toBe(true);
    const mark = root.querySelector("mark.reader-anchor-mark")!;
    expect(mark.textContent).toBe("贪心策略");
    expect(root.textContent).toContain("Dijkstra 属于贪心策略");
  });

  it("says no when the quote is not in the rendered text", () => {
    const root = mount("这一段里没有那句话。");

    expect(highlightQuote(root, "贪心策略")).toBe(false);
    expect(root.querySelectorAll("mark").length).toBe(0);
  });

  it("does not double-wrap the same quote", () => {
    const root = mount("贪心策略 与 贪心策略 都出现了。");

    expect(highlightQuote(root, "贪心策略")).toBe(true);
    expect(highlightQuote(root, "贪心策略")).toBe(true);

    // 同一处不重复包；第二处仍然会被画出来。
    expect(root.querySelectorAll("mark.reader-anchor-mark").length).toBe(2);
    expect(root.querySelectorAll("mark mark").length).toBe(0);
  });

  it("ignores an empty quote", () => {
    const root = mount("随便一段。");

    expect(highlightQuote(root, "   ")).toBe(false);
  });
});

describe("clearHighlights", () => {
  it("unwraps everything it added but keeps the text", () => {
    const root = mount("Dijkstra 属于贪心策略。");
    highlightQuote(root, "贪心策略");

    clearHighlights(root);

    expect(root.querySelectorAll("mark").length).toBe(0);
    expect(root.textContent).toBe("Dijkstra 属于贪心策略。");
  });
});
