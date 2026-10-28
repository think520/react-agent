import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * 接线契约（2026-10-28）。
 * 起因：图谱 4px 指针死区只测了纯函数 → 纯函数全绿，但 dragOrigin 从没被赋值，功能全程空转。
 * 这里从**源码结构**上钉住"必须真的接线"，补上单元测试抓不到的那一层。
 */
const SRC = resolve(process.cwd(), "src");
// 统一成 LF：CRLF 文件用 \n 正则匹配会假失败（这批审查里就踩过同样的坑）。
const read = (path: string) => readFileSync(resolve(SRC, path), "utf8").replace(/\r\n/g, "\n");

describe("源码接线契约", () => {
  const graph = read("components/GraphCanvas.tsx");

  it("图谱死区：downNode 记录起点，moveBody 累计越界，clickNode 拦截", () => {
    expect(graph).toMatch(/renderer\.on\("downNode", \(\{ node, event \}\)/);
    expect(graph).toMatch(/dragOrigin = event \? \{ x: event\.x, y: event\.y \}/);
    expect(graph).toMatch(/dragMoved = false/);
    const moveBody = graph.slice(graph.indexOf('renderer.on("moveBody"'));
    expect(moveBody.slice(0, 400)).toContain("dragMoved = true");
    const clickNode = graph.slice(graph.indexOf('renderer.on("clickNode"'));
    expect(clickNode.slice(0, 400)).toContain("if (dragMoved) return;");
  });

  it("会话切换不得沿用上一个会话的消息：非 justCreated 路径必须 setLoading(true)", () => {
    const chat = read("pages/ChatPage.tsx");
    expect(chat).toContain("justCreatedRef");
    expect(chat).toMatch(/if \(justCreatedRef\.current\) \{[\s\S]{0,200}setLoading\(false\)[\s\S]{0,80}return;/);
    expect(chat).toMatch(/setLoading\(true\);\n\s+void api\.session\(sessionId\)/);
    expect(chat).not.toContain("messagesLatestRef.current.length === 0");
  });

  it("会话创建后的 URL 写入要带 chatSessionJustCreated 标记", () => {
    const actions = read("pages/chat/chatActions.ts");
    const marked = (actions.match(/chatSessionJustCreated/g) ?? []).length;
    expect(marked).toBeGreaterThanOrEqual(4);
  });

  it("首帧主题：index.html 必须在 CSS 之前定主题，且 color-scheme 允许暗色", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8").replace(/\r\n/g, "\n");
    expect(html).toContain("bobodan:theme");
    expect(html).toContain("dataset.theme");
    expect(html).toMatch(/name="color-scheme"\s+content="light dark"/);
    // 预置脚本必须在 module script 之前
    expect(html.indexOf("bobodan:theme")).toBeLessThan(html.indexOf("/src/main.tsx"));
  });

  it("主题解析结果要写回缓存（否则首帧脚本没有真值可用）", () => {
    const shell = read("components/AppShell.tsx");
    expect(shell).toContain('localStorage.setItem("bobodan:theme"');
  });

  it("暗色下纸张纹理的浅色覆盖必须限定浅色主题", () => {
    const css = read("styles/app.css");
    expect(css).toMatch(/\[data-theme="light"\]\[data-paper-texture="off"\]/);
    expect(css).toContain('[data-paper-texture="on"] body { background-color: var(--paper); }');
  });

  it("减动效只零化时长令牌，不用 !important 压属性（组件级规则才能生效）", () => {
    const css = read("styles/app.css");
    expect(css).toMatch(/--dur-fast: 0ms/);
    expect(css).toMatch(/\[data-motion="reduced"\] \{[\s\S]{0,300}--dur-shimmer: 0ms/);
    expect(css).not.toContain("animation-duration: 0.01ms !important");
    expect(css).not.toContain("transition-duration: 0.01ms !important");
    // 组件级规则必须还在（恢复生效的标志）
    expect(css).toContain(".setting-toggle i { transition: none; }");
    // 无限循环动画必须显式停掉，否则 0ms 循环会抖动
    expect(css).toMatch(/\.spin, \.wiki-run-thinking i, \.reader-actions \.status-extracting svg, \.skeleton \{ animation: none; \}/);
  });

  it("缩进契约：路由块与 compositionProps 逐行对齐（防止正则编辑再弄坏）", () => {
    const app = readFileSync(resolve(process.cwd(), "src/App.tsx"), "utf8").replace(/\r\n/g, "\n");
    const routeLines = app.split("\n").filter((line) => line.includes("chat/:sessionId?"));
    expect(routeLines.length).toBe(1);
    expect(routeLines[0].startsWith("            <Route")).toBe(true);
    const chat = read("pages/ChatPage.tsx");
    const composition = chat.split("\n").find((line) => line.includes("{...ime.compositionProps}"));
    expect(composition).toBeDefined();
    expect(composition!.startsWith("          {...ime.compositionProps}")).toBe(true);
  });
  it("不要再出现第二条全局 !important 减动效重拳", () => {
    const css = read("styles/app.css");
    const hits = (css.match(/animation: none !important; transition: none !important/g) ?? []).length;
    expect(hits).toBe(0);
  });
});
