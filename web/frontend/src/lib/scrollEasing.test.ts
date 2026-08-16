import { describe, expect, it } from "vitest";

import {
  INSTANT_JUMP_THRESHOLD,
  TAU_MS,
  easedPosition,
  easingFactor,
  shouldJumpInstant,
} from "./scrollEasing";

describe("easingFactor", () => {
  it("is 0 at zero delta", () => {
    expect(easingFactor(0)).toBe(0);
  });

  it("approaches 1 as delta grows", () => {
    expect(easingFactor(TAU_MS)).toBeCloseTo(1 - Math.exp(-1), 5);
    expect(easingFactor(TAU_MS * 4)).toBeGreaterThan(0.98);
  });

  it("respects custom tau", () => {
    expect(easingFactor(100, 100)).toBeCloseTo(1 - Math.exp(-1), 5);
  });
});

describe("shouldJumpInstant", () => {
  it("jumps for large distances", () => {
    expect(shouldJumpInstant(INSTANT_JUMP_THRESHOLD + 1)).toBe(true);
    expect(shouldJumpInstant(-1000)).toBe(true);
  });

  it("eases for small distances", () => {
    expect(shouldJumpInstant(200)).toBe(false);
  });
});

describe("easedPosition", () => {
  it("moves toward target proportionally", () => {
    expect(easedPosition(0, 100, 0.5)).toBe(50);
    expect(easedPosition(100, 0, 1)).toBe(0);
  });
});
