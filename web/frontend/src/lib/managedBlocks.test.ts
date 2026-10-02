import { describe, expect, it } from "vitest";

import {
  MANAGED_END,
  MANAGED_START,
  readManagedBlock,
  renderHighlightsBlock,
  upsertManagedBlock,
} from "./managedBlocks";

/**
 * W1 E7：笔记里的**托管区块**（自定语法）。
 *
 * 三家参考项目都没有等价机制，所以规则由我们定，而且只有一条最重要的：
 * **只重写标记之间，永不碰用户手写的内容**。
 */

const key = "highlights:doc-1";
const body = "- 「贪心策略」";

describe("upsertManagedBlock", () => {
  it("appends the block when the note does not have one", () => {
    const result = upsertManagedBlock("# 我的笔记\n\n手写内容。", key, body);

    expect(result.changed).toBe(true);
    expect(result.text).toContain("手写内容。");
    expect(result.text).toContain(MANAGED_START(key));
    expect(result.text).toContain(body);
    expect(result.text).toContain(MANAGED_END(key));
  });

  it("replaces only what is between the markers", () => {
    const first = upsertManagedBlock("# 笔记\n\n上面。", key, "- 旧内容").text;
    const manual = first.replace("上面。", "上面。\n\n用户后来手写的一段。");
    const second = upsertManagedBlock(manual, key, "- 新内容");

    expect(second.changed).toBe(true);
    expect(second.text).toContain("用户后来手写的一段。");
    expect(second.text).toContain("- 新内容");
    expect(second.text).not.toContain("- 旧内容");
  });

  it("is idempotent: the same body changes nothing", () => {
    const once = upsertManagedBlock("笔记正文。", key, body).text;
    const twice = upsertManagedBlock(once, key, body);

    expect(twice.changed).toBe(false);
    expect(twice.text).toBe(once);
  });

  it("keeps blocks of different documents apart", () => {
    const first = upsertManagedBlock("笔记。", "highlights:doc-1", "- A").text;
    const second = upsertManagedBlock(first, "highlights:doc-2", "- B");

    expect(second.text).toContain("- A");
    expect(second.text).toContain("- B");
    expect(readManagedBlock(second.text, "highlights:doc-1")).toContain("- A");
    expect(readManagedBlock(second.text, "highlights:doc-2")).toContain("- B");
  });

  it("still appends when a previous block was left unclosed", () => {
    // 用户手抖删掉了结束标记：不能把后面所有内容都当成托管区吞掉。
    const broken = `# 笔记\n${MANAGED_START(key)}\n- 半截\n\n用户手写的结尾。`;
    const result = upsertManagedBlock(broken, key, "- 新内容");

    expect(result.text).toContain("用户手写的结尾。");
    expect(readManagedBlock(result.text, key)).toContain("- 新内容");
  });
});

describe("readManagedBlock", () => {
  it("returns null when there is no block", () => {
    expect(readManagedBlock("普通笔记。", key)).toBeNull();
  });

  it("returns the body between the markers", () => {
    const text = upsertManagedBlock("笔记。", key, "- 一\n- 二").text;

    expect(readManagedBlock(text, key)?.trim()).toBe("- 一\n- 二");
  });
});

describe("renderHighlightsBlock", () => {
  it("lists quotes deterministically and labels moved or stale ones", () => {
    const body = renderHighlightsBlock([
      { quote: "贪心策略", resolution: { status: "exact" } },
      { quote: "换了位置的话", resolution: { status: "relocated", chunk_id: "c9" } },
      { quote: "已经找不到的话", resolution: { status: "stale" } },
    ]);

    expect(body).toContain("贪心策略");
    expect(body).toContain("位置已更新");
    expect(body).toContain("已失效");
    // 同一批输入两次渲染要一致（便于幂等判断）。
    expect(renderHighlightsBlock([
      { quote: "贪心策略", resolution: { status: "exact" } },
      { quote: "换了位置的话", resolution: { status: "relocated", chunk_id: "c9" } },
      { quote: "已经找不到的话", resolution: { status: "stale" } },
    ])).toBe(body);
  });

  it("says so honestly when there is nothing to sync", () => {
    expect(renderHighlightsBlock([])).toContain("还没有划线");
  });
});
