import { describe, expect, it } from "vitest";

import { routeSlashCommand } from "./commandRouter";
import { parseMentionDraft } from "./mention";
import { sessionGroup } from "./sessionGroup";
import { looksLikeSettingsChange } from "./settingsIntent";

describe("chat command routing", () => {
  it("routes navigation and wiki commands", () => {
    expect(routeSlashCommand("/new")).toEqual({ kind: "navigate", to: "/chat" });
    expect(routeSlashCommand("/wiki plan 整理第一章")).toEqual({
      kind: "wiki-focus",
      action: "generate",
      instruction: "整理第一章",
    });
    expect(routeSlashCommand("/wiki update")).toEqual({
      kind: "wiki-focus",
      action: "update",
      instruction: "",
    });
  });

  it("routes practice and web search without swallowing ordinary text", () => {
    expect(routeSlashCommand("/quiz generate 注意力机制")).toEqual({
      kind: "practice-topic",
      topic: "注意力机制",
    });
    expect(routeSlashCommand("/web search")).toEqual({ kind: "web-search-empty" });
    expect(routeSlashCommand("Transformer 最新进展", { webOnce: true })).toEqual({
      kind: "web-search",
      query: "Transformer 最新进展",
    });
    expect(routeSlashCommand("解释注意力机制")).toEqual({ kind: "none" });
  });
});

describe("chat mention parsing", () => {
  it("recognizes document and session shortcuts", () => {
    expect(parseMentionDraft("@")).toEqual({ raw: "", query: "", forcedTab: null });
    expect(parseMentionDraft("引用 @资料")).toEqual({ raw: "资料", query: "", forcedTab: "document" });
    expect(parseMentionDraft("继续 @会话")).toEqual({ raw: "会话", query: "", forcedTab: "session" });
  });

  it("only matches a trailing mention outside slash commands", () => {
    expect(parseMentionDraft("引用 @Transformer")).toEqual({
      raw: "Transformer",
      query: "transformer",
      forcedTab: null,
    });
    expect(parseMentionDraft("/wiki @资料")).toBeNull();
    expect(parseMentionDraft("@资料 后续文字")).toBeNull();
  });
});

describe("settings intent detection", () => {
  it("normalizes whitespace for known settings phrases", () => {
    expect(looksLikeSettingsChange("请把回答 简短 一点")).toBe(true);
    expect(looksLikeSettingsChange("以后反馈温和一点")).toBe(true);
  });

  it("does not classify ordinary knowledge questions as settings changes", () => {
    expect(looksLikeSettingsChange("为什么注意力机制适合长文本？")).toBe(false);
  });
});

describe("session date grouping", () => {
  const now = new Date(2026, 6, 22, 12, 0, 0);

  it("groups dates relative to the current local week", () => {
    expect(sessionGroup("2026-07-22T08:00:00", now)).toBe("今天");
    expect(sessionGroup("2026-07-21T08:00:00", now)).toBe("昨天");
    expect(sessionGroup("2026-07-20T08:00:00", now)).toBe("本周");
    expect(sessionGroup("2026-07-19T08:00:00", now)).toBe("更早");
  });

  it("puts invalid timestamps in the oldest group", () => {
    expect(sessionGroup("not-a-date", now)).toBe("更早");
  });
});
