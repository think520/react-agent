import { describe, expect, it } from "vitest";

import { difficultyLabel, questionTypeLabel } from "./practiceCards";

/**
 * W1 E5：实时卡片要把题型/难度显示成中文。**不认识的取值如实显示原值** ——
 * 编一个中文标签会让用户以为系统懂这个类型。
 */

describe("questionTypeLabel", () => {
  it("translates the known types", () => {
    expect(questionTypeLabel("single_choice")).toBe("单选题");
    expect(questionTypeLabel("multiple_choice")).toBe("多选题");
    expect(questionTypeLabel("short_answer")).toBe("简答题");
    expect(questionTypeLabel("true_false")).toBe("判断题");
  });

  it("shows an unknown type as-is instead of inventing a label", () => {
    expect(questionTypeLabel("matching")).toBe("matching");
    expect(questionTypeLabel("")).toBe("");
    expect(questionTypeLabel(undefined)).toBe("");
  });
});

describe("difficultyLabel", () => {
  it("translates the known levels", () => {
    expect(difficultyLabel("easy")).toBe("简单");
    expect(difficultyLabel("medium")).toBe("中等");
    expect(difficultyLabel("hard")).toBe("较难");
  });

  it("is honest about unknown or missing levels", () => {
    expect(difficultyLabel("impossible")).toBe("impossible");
    expect(difficultyLabel("")).toBe("");
    expect(difficultyLabel(undefined)).toBe("");
  });
});
