import { describe, expect, it } from "vitest";

import { masteryLabel, nextObjectiveText } from "./reviewObjective";

/**
 * W1 E6 接线：引擎算出来的东西要**说清楚**在界面上 ——
 * 包括「这是推导的还是老数据里的存量」。
 */

describe("nextObjectiveText", () => {
  it("says nothing when there is nothing to do", () => {
    expect(nextObjectiveText(null)).toBe("");
    expect(nextObjectiveText(undefined)).toBe("");
  });

  it("puts a pending question first", () => {
    expect(nextObjectiveText({ kind: "pending_question", prompt: "先学极限还是导数？" }))
      .toContain("先回答");
  });

  it("names the due concept", () => {
    expect(nextObjectiveText({ kind: "due_review", concept: "极限" })).toContain("「极限」");
  });

  it("names the concept to learn next", () => {
    expect(nextObjectiveText({ kind: "unseen_concept", concept: "导数" })).toContain("「导数」");
  });
});

describe("masteryLabel", () => {
  it("marks a derived score and how much evidence it has", () => {
    const label = masteryLabel({ mastery: 0.5, evidence: 1, mastery_source: "history" });
    expect(label).toContain("0.5");
    expect(label).toContain("1 次");
  });

  it("warns that a stored score has no attempt history", () => {
    const label = masteryLabel({ mastery: 0.7, evidence: 0, mastery_source: "stored" });
    expect(label).toContain("0.7");
    expect(label).toContain("存量");
  });

  it("stays empty when the payload has no mastery at all", () => {
    expect(masteryLabel({})).toBe("");
  });
});
