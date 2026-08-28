import { describe, expect, it } from "vitest";

import { EMPTY_ARRAY, makeSessionScopedSelector, normalizeSessionKey, sessionScopedValue } from "./selector";

describe("session-scoped selector helpers", () => {
  it("normalizes undefined session ids to an empty string", () => {
    expect(normalizeSessionKey(undefined)).toBe("");
    expect(normalizeSessionKey(null)).toBe("");
    expect(normalizeSessionKey("abc")).toBe("abc");
  });

  it("returns the per-session list when present", () => {
    const map = { "": [{ id: "a" }], abc: [{ id: "b" }] };
    expect(sessionScopedValue(map, undefined)).toEqual([{ id: "a" }]);
    expect(sessionScopedValue(map, "abc")).toEqual([{ id: "b" }]);
  });

  it("returns a stable empty array for missing entries", () => {
    expect(sessionScopedValue({}, "missing")).toBe(EMPTY_ARRAY);
    expect(sessionScopedValue(undefined, "missing")).toBe(EMPTY_ARRAY);
  });

  it("does not leak one session's list into another", () => {
    const map = { abc: [{ id: "a" }] };
    expect(sessionScopedValue(map, "other")).toBe(EMPTY_ARRAY);
  });

  it("builds a selector that is independent of unrelated sessions", () => {
    const selector = makeSessionScopedSelector("abc");
    const state = { abc: [{ id: "a" }], other: [{ id: "z" }] };
    expect(selector(state)).toEqual([{ id: "a" }]);
    // Stable identity across calls for the same key.
    expect(selector(state)).toBe(selector(state));
  });
});
