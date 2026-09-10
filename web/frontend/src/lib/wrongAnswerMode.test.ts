import { describe, expect, it } from "vitest";

import { wrongAnswerFallbackNotice } from "./wrongAnswerMode";

describe("wrongAnswerFallbackNotice", () => {
  it("says nothing for a real variant", () => {
    expect(wrongAnswerFallbackNotice("variant")).toBeNull();
    expect(wrongAnswerFallbackNotice(undefined)).toBeNull();
  });

  it("explains the concept fallback", () => {
    expect(wrongAnswerFallbackNotice("concept_fallback")).toContain("同一概念");
  });

  it("explains the original-question replay", () => {
    expect(wrongAnswerFallbackNotice("replay")).toContain("原题");
  });
});
