import { describe, expect, it } from "vitest";

import { describeDocumentImport } from "./importSummary";

describe("describeDocumentImport", () => {
  it("does not claim that an empty PDF was indexed", () => {
    expect(describeDocumentImport({
      imported: ["blank.pdf"], rejected: [],
      sync: { extraction_counts: { complete: 0, partial: 0, empty: 1, error: 0 }, error_files: 0 },
    })).toBe("已接收 1 份文件，1 份没有可提取文本。");
  });

  it("reports searchable, failed and rejected files separately", () => {
    expect(describeDocumentImport({
      imported: ["a.md", "b.pdf", "broken.pdf"], rejected: ["x.exe"],
      sync: { extraction_counts: { complete: 1, partial: 1, empty: 0, error: 1 }, error_files: 1 },
    })).toBe("已接收 3 份文件，2 份可用于检索，1 份解析失败，1 份未导入。");
  });

  it("makes an identical upload decision visible", () => {
    expect(describeDocumentImport({
      imported: [], duplicates: ["lesson-copy.md"], rejected: [],
      sync: { extraction_counts: {}, error_files: 0 },
    })).toBe("已接收 0 份文件，1 份重复文件已保留已有版本。");
  });
});
