import { describe, expect, it } from "vitest";

import type { ChatMessage } from "../types";
import { buildFollowUpSuggestions } from "./chatFollowUps";

describe("buildFollowUpSuggestions", () => {
  it("returns empty array for non-assistant, pending, failed, stopped, or blank messages", () => {
    expect(buildFollowUpSuggestions({ role: "user", content: "hi" })).toEqual([]);
    expect(buildFollowUpSuggestions({ role: "assistant", content: "正在写", pending: true })).toEqual([]);
    expect(buildFollowUpSuggestions({ role: "assistant", content: "出错了", failed: true })).toEqual([]);
    expect(buildFollowUpSuggestions({ role: "assistant", content: "停止了", stopped: true })).toEqual([]);
    expect(buildFollowUpSuggestions({ role: "assistant", content: "   " })).toEqual([]);
  });

  it("adapts follow-up labels for grounded vs ungrounded dense replies", () => {
    const denseGrounded: ChatMessage = {
      role: "assistant",
      content: "## 推导过程\n\n" + "内容".repeat(160),
      attribution: { kind: "local", status: "found", sources: [] },
    };
    const groundedChips = buildFollowUpSuggestions(denseGrounded);
    expect(groundedChips.map((item) => item.label)).toEqual(["换个直觉类比", "列出易混淆点", "对照资料补全推导"]);

    const shortUngrounded: ChatMessage = {
      role: "assistant",
      content: "这是一句简要说明。",
    };
    const ungroundedChips = buildFollowUpSuggestions(shortUngrounded);
    expect(ungroundedChips.map((item) => item.label)).toEqual(["展开讲关键细节", "举一个具体例子", "出 2 道小题考我"]);
  });
});
