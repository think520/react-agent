import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const APP_CSS = readFileSync(resolve(process.cwd(), "src/styles/app.css"), "utf8");

function readSource(path: string): string {
  return readFileSync(resolve(process.cwd(), "src", path), "utf8");
}

function ruleBody(selector: string): string {
  const match = APP_CSS.match(new RegExp(`(?:^|\\n)${selector.replace(".", "\\.")} \\{([^}]*)\\}`));
  return match?.[1] || "";
}

describe("设置对话框视口约束", () => {
  it("最大高度不会压过最小高度，低高度视口仍能滚动到动作区", () => {
    const dialog = ruleBody(".settings-dialog");
    expect(dialog).toContain("max-height: min(84vh, 840px)");
    expect(dialog).toContain("min-height: min(620px, calc(100dvh - 40px))");
    expect(ruleBody(".settings-main")).toContain("overflow-y: auto");
  });

  it("助手设置的主操作在对话框底部，不依赖内容区滚到底", () => {
    const footer = ruleBody(".settings-dialog-footer");
    expect(footer).toContain("flex: 0 0 auto");
    expect(footer).toContain("border-top");
    const dialogSource = readSource("components/SettingsDialog.tsx");
    expect(dialogSource).toContain('className="settings-dialog-footer"');
    expect(dialogSource).toContain("saveAssistant()");
  });
});
