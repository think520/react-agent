import { describe, expect, it } from "vitest";

import { distinctExplanation } from "./practiceFeedback";

describe("distinctExplanation", () => {
  it("hides a legacy explanation already embedded in feedback", () => {
    expect(distinctExplanation("错误。正确答案是 B。 因为边权非负。", "因为边权非负。")).toBe("");
  });

  it("keeps a separate explanation when feedback only contains the verdict", () => {
    expect(distinctExplanation("错误。正确答案是 B。", "因为边权非负。")).toBe("因为边权非负。");
  });
});
