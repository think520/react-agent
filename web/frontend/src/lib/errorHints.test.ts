import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { errorCodeOf, errorHint, userMessageFor } from "./errorHints";

/**
 * W1 E1：错误码要**上屏**（以前只显示后端文案，界面分不清"可重试 / 需配置 / 需重接资料库"）。
 *
 * 原则：只对"用户有明确下一步"的 code 给提示；不认识的 code **不编**建议
 * （后端文案已经说明了发生了什么）。
 */

describe("errorHint", () => {
  it("gives the next step for codes the user can act on", () => {
    expect(errorHint("grading_unavailable")).toContain("稍后重试");
    expect(errorHint("provider_unconfigured")).toContain("设置");
    expect(errorHint("unsupported_file_type")).toContain("Markdown");
    expect(errorHint("library_unavailable")).toContain("资料库");
  });

  it("tells the user what to do when a session cannot be opened (2026-11-11)", () => {
    expect(errorHint("session_not_found")).toContain("新会话");
    expect(errorHint("session_corrupt")).toContain("删除");
    expect(errorHint("session_ambiguous")).toContain("左侧列表");
    expect(errorHint("knowledge_item_not_found")).toContain("刷新");
    expect(errorHint("session_delete_failed")).toContain("再试");
  });

  it("says nothing when it does not know the code", () => {
    expect(errorHint("some_brand_new_code")).toBe("");
    expect(errorHint(undefined)).toBe("");
  });

  it("does not invent advice for generic failures", () => {
    expect(errorHint("request_failed")).toBe("");
  });
});

describe("errorCodeOf", () => {
  it("reads the structured code off an ApiError", () => {
    expect(errorCodeOf(new ApiError("目标文件夹已存在", "library_unavailable", 409))).toBe("library_unavailable");
  });

  it("accepts any error carrying a string code", () => {
    const error = Object.assign(new Error("x"), { code: "grading_unavailable" });
    expect(errorCodeOf(error)).toBe("grading_unavailable");
  });

  it("returns empty for plain errors and non-errors", () => {
    expect(errorCodeOf(new Error("x"))).toBe("");
    expect(errorCodeOf("boom")).toBe("");
    expect(errorCodeOf(undefined)).toBe("");
  });
});


describe("userMessageFor", () => {
  it("prefers the actionable hint over the raw backend message", () => {
    expect(userMessageFor(new ApiError("Session not found: x", "session_not_found", 404), "兜底")).toContain("新会话");
  });

  it("falls back to the backend message, then to the default", () => {
    expect(userMessageFor(new ApiError("磁盘已满", "request_failed", 500), "兜底")).toBe("磁盘已满");
    expect(userMessageFor("not an error", "兜底")).toBe("兜底");
  });
});
