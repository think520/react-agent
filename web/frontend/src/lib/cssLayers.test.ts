import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * M1 CSS 分层的**结构契约**（2026-10-17）。
 *
 * 目的不是「检查代码风格」，而是钉住三件容易被后续改动悄悄破坏的事：
 * 1) 入口保持很小（≤120 行），别再把几千行规则塞回去；
 * 2) 字体声明只在 fonts.css 里，且只能本地 URL（关键 CSS 不含字体，首屏不被 40MB 字体拖住）；
 * 3) 令牌只在 tokens.css 的 :root 里定义一份（app.css 不得再冒出一个 :root）。
 */

const SRC = resolve(process.cwd(), "src");
const read = (relative: string) => readFileSync(resolve(SRC, relative), "utf8");

describe("CSS 分层契约（M1）", () => {
  it("入口 styles.css ≤ 120 行，且只做 @import 编排", () => {
    const entry = read("styles.css");
    expect(entry.split("\n").length).toBeLessThanOrEqual(120);
    expect(entry).toContain('@import "tailwindcss"');
    expect(entry).toContain("./styles/tokens.css");
    expect(entry).toContain("./styles/app.css");
    expect(entry).not.toContain("@font-face");
    expect(read("styles/app.css")).not.toContain("@font-face");
  });

  it("字体声明只在 fonts.css，且全部本地 URL、无公共 CDN", () => {
    const fonts = read("styles/fonts.css");
    expect((fonts.match(/@font-face/g) || []).length).toBeGreaterThanOrEqual(3);
    expect(fonts).toContain("Luo-Regular.woff2");
    expect(fonts).toContain("TsangerJinKai02");
    for (const banned of ["fonts.googleapis.com", "fonts.gstatic.com", "jsdelivr", "unpkg"]) {
      expect(fonts.includes(banned)).toBe(false);
    }
    expect(/url\(\s*["']?https?:/i.test(fonts)).toBe(false);
  });

  it("字体是异步加载的，不在 main.tsx 静态导入", () => {
    const main = read("main.tsx");
    expect(main).toContain('import("./styles/fonts.css")');
    expect(main).not.toContain('import "./noto-serif-sc.css"');
    expect(main).not.toContain('import "./styles/fonts.css"');
  });

  it("令牌只定义一份：tokens.css 有 :root，app.css 没有", () => {
    expect(read("styles/tokens.css")).toContain(":root");
    expect(read("styles/tokens.css")).toContain("--paper:");
    expect(read("styles/app.css")).not.toMatch(/^:root\s*\{/m);
  });
});
