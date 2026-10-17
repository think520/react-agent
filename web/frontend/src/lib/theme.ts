/** 主题解析（W-F6）：偏好只决定「想用哪种」，落到 DOM 上必须是明确的 light / dark。 */
export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export function resolveTheme(preference: ThemePreference, systemPrefersDark: boolean): ResolvedTheme {
  if (preference === "system") return systemPrefersDark ? "dark" : "light";
  return preference;
}

export function systemPrefersDark(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches === true;
}

/** 跟随系统主题时，系统切换要实时反映到界面；返回取消订阅函数。 */
export function watchSystemTheme(onChange: (prefersDark: boolean) => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => undefined;
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  const listener = (event: MediaQueryListEvent) => onChange(event.matches);
  if (typeof query.addEventListener === "function") {
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }
  return () => undefined;
}
