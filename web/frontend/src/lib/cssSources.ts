import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * 测试专用：按 `styles/app.css` 里的 @import 顺序读出全部页面样式（2026-11-11 app.css 拆分后）。
 * 契约测试以前直接读 app.css；拆开之后必须读拼接结果，否则「规则搬了家」会让断言静默失义。
 */
const STYLES = resolve(process.cwd(), "src", "styles");

export function appCssFiles(): string[] {
  const index = readFileSync(resolve(STYLES, "app.css"), "utf8");
  return [...index.matchAll(/@import\s+"\.\/([^"]+)"/g)].map((match) => match[1]);
}

export function readAppCss(): string {
  return appCssFiles().map((name) => readFileSync(resolve(STYLES, name), "utf8")).join("\n");
}
