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

  // W1 E3：reason 比 mode 精确 —— 证据缺失 / 生成失败 / 未配置模型是三件事。
  it("distinguishes missing evidence from a failed generation", () => {
    const missing = wrongAnswerFallbackNotice("concept_fallback", "evidence_missing");
    const failed = wrongAnswerFallbackNotice("concept_fallback", "variant_failed");
    expect(missing).toContain("证据已失效");
    expect(failed).toContain("变式生成失败");
    expect(failed).not.toContain("证据已失效");
  });

  it("says the model is not configured instead of blaming the evidence", () => {
    const notice = wrongAnswerFallbackNotice("replay", "no_provider");
    expect(notice).toContain("模型未配置");
    expect(notice).not.toContain("证据");
  });

  it("keeps working when an older backend sends only a mode", () => {
    expect(wrongAnswerFallbackNotice("concept_fallback", undefined)).toContain("同一概念");
    expect(wrongAnswerFallbackNotice("replay")).toContain("原题");
  });
});
