import { describe, expect, it } from "vitest";

import { practiceSummaryLine } from "./practiceSummary";

/**
 * W1 E15：练习小结不能与事实相反。
 *
 * 错题谓词**排除 partial**（quiz/store.py 的 _WRONG_VERDICT_SQL），所以"只有 partial"的一轮
 * 根本没有新增错题；旧文案却一律说"错题和薄弱点已经加入复习队列"。
 */

describe("practiceSummaryLine", () => {
  it("全对时明说没有新增错题", () => {
    const line = practiceSummaryLine({ correct: 3, partial: 0, wrong: 0, total: 3 });
    expect(line).toContain("答对 3 / 3 题");
    expect(line).toContain("全部答对，复习队列没有新增错题");
  });

  it("只有 partial 时不说'错题已入队'（它压根没进错题本）", () => {
    const line = practiceSummaryLine({ correct: 2, partial: 1, wrong: 0, total: 3 });
    expect(line).toContain("答对 2 / 3 题");
    expect(line).toContain("另有 1 题基本正确");
    expect(line).toContain("计入薄弱点");
    expect(line).toContain("没有进错题本");
    expect(line).not.toContain("错题和薄弱点已经加入复习队列");
  });

  it("真的答错时才说错题已入队", () => {
    const line = practiceSummaryLine({ correct: 1, partial: 1, wrong: 1, total: 3 });
    expect(line).toContain("答对 1 / 3 题");
    expect(line).toContain("另有 1 题基本正确");
    expect(line).toContain("错题和薄弱点已经加入复习队列");
  });

  it("老数据缺字段时按'没有 partial/错题'处理，不瞎猜", () => {
    const line = practiceSummaryLine({ correct: 1, total: 2 });
    expect(line).toContain("答对 1 / 2 题");
    expect(line).not.toContain("错题和薄弱点已经加入复习队列");
  });
});
