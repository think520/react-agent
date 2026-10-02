import { describe, expect, it } from "vitest";

import { describeDocumentImport, describeImportOutcome } from "./importSummary";

/**
 * 导入结果文案。
 *
 * 2026-09-28 审查 F09：这里原来拿**全库增量同步**的统计当本次上传的计数，
 * 于是"上传 1 份"会显示成"2 份可用于检索"（资料库里别的文件也在这次同步里）。
 * 下面的用例钉住：批次计数只看本次上传的逐文件结果，全库增量单独一句。
 */

describe("describeDocumentImport", () => {
  it("does not claim that an empty PDF was indexed", () => {
    expect(describeDocumentImport({
      imported: ["blank.pdf"], rejected: [],
      results: [{ filename: "blank.pdf", status: "imported", searchable: false, extraction: "empty" }],
      library_sync: { extraction_counts: { empty: 1 }, error_files: 0 },
    })).toBe("已接收 1 份文件，1 份没有可提取文本。");
  });

  it("reports searchable, failed and rejected files separately", () => {
    expect(describeDocumentImport({
      imported: ["a.md", "b.pdf", "broken.pdf"], rejected: ["x.exe"],
      results: [
        { filename: "a.md", status: "imported", searchable: true, extraction: "complete" },
        { filename: "b.pdf", status: "imported", searchable: true, extraction: "partial" },
        { filename: "broken.pdf", status: "imported", searchable: false, extraction: "error" },
        { filename: "x.exe", status: "rejected" },
      ],
      library_sync: { extraction_counts: { complete: 1, partial: 1, error: 1 }, error_files: 1 },
    })).toBe("已接收 3 份文件，2 份可用于检索，1 份解析失败，1 份未导入。");
  });

  it("makes an identical upload decision visible", () => {
    expect(describeDocumentImport({
      imported: [], duplicates: ["lesson-copy.md"], rejected: [],
      results: [{ filename: "lesson-copy.md", status: "duplicate" }],
      library_sync: { extraction_counts: {}, error_files: 0 },
    })).toBe("已接收 0 份文件，1 份重复文件已保留已有版本。");
  });

  // F09 的复现：改动资料库里另一份文件 + 上传 1 份新文件时，界面曾经说"2 份可用于检索"。
  it("counts only this batch, and lists the library-wide delta separately", () => {
    const text = describeDocumentImport({
      imported: ["new.md"], duplicates: [], rejected: [], pending: [],
      results: [{ filename: "new.md", status: "imported", searchable: true, extraction: "complete" }],
      library_sync: { extraction_counts: { complete: 2 }, error_files: 0 },
    });
    expect(text).toContain("已接收 1 份文件");
    expect(text).toContain("1 份可用于检索");
    expect(text).not.toContain("2 份可用于检索");
    expect(text).toContain("资料库里其它 1 份资料");
  });

  // F04 的重试路径：字节已经在库里、这次是补做索引 —— 文案必须说清楚，不能假装"重复已保留"。
  it("says a pending re-index instead of pretending the file was already done", () => {
    const text = describeDocumentImport({
      imported: [], duplicates: [], rejected: [],
      pending: [{ filename: "retry.md", existing: "retry.md" }],
      results: [{ filename: "retry.md", status: "pending", searchable: true, extraction: "complete" }],
      library_sync: { extraction_counts: { complete: 1 }, error_files: 0 },
    });
    expect(text).toContain("1 份在等待建立索引");
    expect(text).toContain("1 份可用于检索");
  });
});
describe("describeImportOutcome（E8：逐文件失败清单的文案）", () => {
  it("把每种结果说成人话，并给出可行动的原因", () => {
    expect(describeImportOutcome({ filename: "a.md", status: "imported", searchable: true }))
      .toBe("已入库，可用于检索");
    expect(describeImportOutcome({ filename: "b.pdf", status: "imported", searchable: false, extraction: "empty" }))
      .toBe("已入库，但这份文件没有可提取的文本");
    expect(describeImportOutcome({ filename: "c.pdf", status: "imported", searchable: false, extraction: "error" }))
      .toBe("解析失败：没能从这份文件里提取出文本");
    expect(describeImportOutcome({ filename: "d.md", status: "pending", reason: "awaiting_index" }))
      .toBe("库里已有相同内容，正在补建索引");
    expect(describeImportOutcome({ filename: "e.md", status: "indexed" }))
      .toBe("已补齐索引，可用于检索");
    expect(describeImportOutcome({ filename: "f.md", status: "duplicate", existing: "Lessons/f.md" }))
      .toBe("与库里的「Lessons/f.md」内容完全相同，已保留已有版本");
    expect(describeImportOutcome({ filename: "g.exe", status: "rejected", reason: "unsupported_file_type" }))
      .toBe("格式不支持（可用 .md / .txt / .pdf / .docx / .pptx）");
    expect(describeImportOutcome({ filename: "h.md", status: "cancelled" }))
      .toBe("已取消，没有导入");
  });

  it("未知结果不装作知道", () => {
    expect(describeImportOutcome({ filename: "x.md", status: "mystery" })).toBe("结果未知");
  });
});

describe("describeDocumentImport 的取消口径", () => {
  it("取消时说清楚'已收下几份、其余未处理'", () => {
    const text = describeDocumentImport({
      imported: ["a.md"], duplicates: [], rejected: [], cancelled: true,
      results: [{ filename: "a.md", status: "imported", searchable: true }],
      library_sync: { extraction_counts: { complete: 1 }, error_files: 0 },
    });
    expect(text).toContain("导入已取消");
    expect(text).toContain("已收下 1 份");
  });
});
