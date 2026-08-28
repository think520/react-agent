import { describe, expect, it } from "vitest";

import { PROCESS_FOLD_THRESHOLD, foldProcess } from "./processFold";

const steps = (n: number) => Array.from({ length: n }, (_, i) => ({ phase: "running", message: "步骤" + (i + 1) }));

describe("foldProcess", () => {
  it("does not fold below the threshold", () => {
    const result = foldProcess(steps(2));
    expect(result.folded).toBe(false);
    expect(result.summary).toBe("步骤1 · 步骤2");
  });

  it("folds at or above the threshold", () => {
    const result = foldProcess(steps(PROCESS_FOLD_THRESHOLD));
    expect(result.folded).toBe(true);
    expect(result.summary).toContain("共 3 个步骤");
  });

  it("treats undefined as empty", () => {
    const result = foldProcess(undefined);
    expect(result.folded).toBe(false);
    expect(result.steps).toEqual([]);
  });
});
