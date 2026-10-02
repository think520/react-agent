import { describe, expect, it } from "vitest";

import { clearImportReport, emptyDocumentImport } from "./importState";

/**
 * W1 E1：切库时"属于上一个资料库"的导入状态必须清掉。
 *
 * 留着会串库：上一库的失败清单还挂在页面上，点「重试这 N 份」会把文件导进**新**资料库。
 */

describe("clearImportReport", () => {
  it("drops the report, notice and counts from the previous library", () => {
    const before = {
      ...emptyDocumentImport(),
      notice: "已收下 2 份",
      error: "有 1 份失败",
      errorCode: "unsupported_file_type",
      duplicateCount: 2,
      importing: true,
      results: [{ filename: "旧库.md", status: "rejected" }],
    };

    const after = clearImportReport(before);

    expect(after.notice).toBe("");
    expect(after.error).toBe("");
    expect(after.errorCode).toBe("");
    expect(after.duplicateCount).toBe(0);
    expect(after.importing).toBe(false);
    expect(after.results).toBeNull();
  });

  it("starts from a clean state", () => {
    const state = emptyDocumentImport();
    expect(state.results).toBeNull();
    expect(state.notice).toBe("");
    expect(state.importing).toBe(false);
  });
});
