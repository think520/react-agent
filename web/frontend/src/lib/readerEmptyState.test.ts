import { describe, expect, it } from "vitest";

import { readerEmptyState } from "./readerEmptyState";

describe("reader empty state", () => {
  it("distinguishes failed extraction from an empty document", () => {
    expect(readerEmptyState({ extraction_status: "error", has_original: true }).title).toBe("原文提取失败");
    expect(readerEmptyState({ extraction_status: "empty", has_original: true }).title).toBe("没有提取到可阅读文本");
    expect(readerEmptyState({ extraction_status: "error", has_original: false }).description).toContain("无法读取原件");
  });

  it("does not claim the index is still building after a successful empty result", () => {
    const empty = readerEmptyState({ extraction_status: "complete", has_original: false });
    expect(empty.title).toBe("暂时没有可阅读的片段");
    expect(empty.description).not.toContain("建立索引");
  });
});
