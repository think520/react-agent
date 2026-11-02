import type { Page } from "@playwright/test";

/** e2e 共享的 API mock：偏好默认值 + 一组**只读**的假后端响应。
 *
 * 存在理由（2026-11-02 审查 P2）：settingsPayload 曾在 4 个 spec 里各写一份，
 * 并且已经漂移 —— settings-fit 的 preferences 缺 theme / contrast，其他有。
 * 偏好字段一旦不同步，L2 主题契约就会在某些 spec 里静默失去意义，所以统一到这里。 */

export const json = (body: unknown) => ({ contentType: "application/json", body: JSON.stringify(body) });

/** 每次调用都返回**新对象**，调用方可以随意改写而不污染其他用例。 */
export function preferences(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 4,
    revision: 0,
    assistant: { display_name: "Bobodan", teaching_style: "guided", answer_depth: "standard", feedback_strength: "gentle" },
    user: { display_name: "", profile: "", long_term_goal: "" },
    appearance: { reading_font: "jin-kai", body_font_size: 16, content_width: 720, paper_texture: true, session_density: "comfortable", motion: "system", theme: "light", contrast: "normal" },
    ai: { default_provider: "deepseek", task_providers: { wiki_discovery: "default", wiki_drafting: "default" } },
    wiki: { default_mode: "standard", guide_completed: false, budget: { max_requests: 24, max_input_tokens: 300000, max_output_tokens: 40000 } },
    memory: { enabled: true },
    search: { provider: "auto", permission: "ask", jina_fallback: true },
    skills: { enabled_names: [] },
    ...overrides,
  };
}

export function settingsPayload(overrides: Record<string, unknown> = {}) {
  return {
    workspace_name: "测试空间",
    default_provider: "deepseek",
    providers: [{ name: "deepseek", configured: true, model: "deepseek-chat" }],
    search_providers: [{ name: "auto", configured: true }, { name: "tavily", configured: false }, { name: "exa", configured: true }],
    mcp_enabled: false,
    skills: [],
    preferences: preferences(),
    ...overrides,
  };
}

export interface MockApiOptions {
  /** 整体替换 /api/settings 的返回体（给需要动态改写的用例）。 */
  settings?: Record<string, unknown>;
  /** 按组覆盖偏好（浅合并 appearance 之外的组用 preferences 覆盖）。 */
  preferences?: Record<string, unknown>;
  /** 只覆盖 appearance 里的字段（主题、对比度、字号…）。 */
  appearance?: Record<string, unknown>;
  /** 是否写入 onboarding 完成标记，默认 true。 */
  onboarding?: boolean;
}

/** 安装每个 mock 规格都需要的最小外壳路由；返回当次生效的 settings 返回体。 */
export async function mockApi(page: Page, options: MockApiOptions = {}) {
  if (options.onboarding !== false) {
    await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  }
  const base = preferences();
  const mergedPreferences = {
    ...base,
    ...(options.preferences || {}),
    appearance: { ...base.appearance, ...(options.appearance || {}) },
  };
  const settings = options.settings || settingsPayload({ preferences: mergedPreferences });

  await page.route("**/api/health", (route) => route.fulfill(json({ ok: true })));
  await page.route("**/api/libraries", (route) => route.fulfill(json({
    active_library_id: "library-1",
    libraries: [{ library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true }],
  })));
  await page.route("**/api/settings", (route) => route.fulfill(json(settings)));
  await page.route("**/api/chat/sessions", (route) => route.fulfill(json({ sessions: [] })));
  await page.route("**/api/kb/documents?collection=all", (route) => route.fulfill(json({ documents: [] })));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill(json({ documents: [] })));
  await page.route("**/api/kb/wiki/coverage", (route) => route.fulfill(json({ documents: [], counts: { uncovered: 0, partial: 0, covered: 0, stale: 0 } })));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill(json({ due_concepts: [], wrong_answers: [], weaknesses: [], personalization: [] })));
  await page.route("**/api/quiz/sessions/active", (route) => route.fulfill(json({ sessions: [] })));
  return settings;
}
