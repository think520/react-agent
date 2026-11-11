import { useEffect } from "react";

import { resolveTheme, systemPrefersDark, watchSystemTheme } from "../lib/theme";
import type { SettingsSummary } from "../types";

/**
 * 把外观偏好写到 <html>（主题、对比度、字体、字号、内容宽度…），主题跟随系统时实时切换。
 * 2026-11-11 从 AppShell 原样拆出：它只写 DOM，不产生任何 React 状态。
 */
export function useAppearanceSync(settings: SettingsSummary | null) {
  useEffect(() => {
    if (!settings) return;
    const appearance = settings.preferences.appearance;
    const root = document.documentElement;
    root.dataset.readingFont = appearance.reading_font;
    root.dataset.paperTexture = appearance.paper_texture ? "on" : "off";
    root.dataset.sessionDensity = appearance.session_density;
    root.dataset.motion = appearance.motion;
    const resolvedTheme = resolveTheme(appearance.theme ?? "system", systemPrefersDark());
    root.dataset.theme = resolvedTheme;
    root.style.colorScheme = resolvedTheme;
    // 缓存解析结果：下次首帧由 index.html 的内联脚本直接读，避免暗色白闪。
    try { localStorage.setItem("bobodan:theme", resolvedTheme); } catch { /* 无痕模式忽略 */ }
    root.dataset.contrast = appearance.contrast === "high" ? "high" : "normal";
    root.style.setProperty("--body-font-size", `${appearance.body_font_size}px`);
    root.style.setProperty("--content-width", `${appearance.content_width}px`);
  }, [settings]);

  // 主题 = 跟随系统时，系统切换要实时反映（W-F6）。
  useEffect(() => {
    if (!settings) return;
    if ((settings.preferences.appearance.theme ?? "system") !== "system") return;
    return watchSystemTheme((prefersDark) => {
      const next = prefersDark ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      document.documentElement.style.colorScheme = next;
      try { localStorage.setItem("bobodan:theme", next); } catch { /* 忽略 */ }
    });
  }, [settings]);
}
