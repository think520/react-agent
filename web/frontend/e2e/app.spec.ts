import { expect, test } from "@playwright/test";

function settingsPayload(overrides: Record<string, unknown> = {}) {
  return {
    workspace_name: "测试空间",
    default_provider: "deepseek",
    providers: [{ name: "deepseek", configured: true, model: "deepseek-chat" }],
    search_providers: [{ name: "auto", configured: true }, { name: "tavily", configured: false }, { name: "exa", configured: true }],
    mcp_enabled: false,
    skills: [],
    preferences: {
      schema_version: 4,
      revision: 0,
      assistant: { display_name: "Bobodan", teaching_style: "guided", answer_depth: "standard", feedback_strength: "gentle" },
      user: { display_name: "", profile: "", long_term_goal: "" },
      appearance: { reading_font: "jin-kai", body_font_size: 16, content_width: 720, paper_texture: true, session_density: "comfortable", motion: "system" },
      ai: { default_provider: "deepseek", task_providers: { wiki_discovery: "default", wiki_drafting: "default" } },
      wiki: { default_mode: "standard", guide_completed: false, budget: { max_requests: 24, max_input_tokens: 300000, max_output_tokens: 40000 } },
      memory: { enabled: true },
      search: { provider: "auto", permission: "ask", jina_fallback: true },
      skills: { enabled_names: [] },
    },
    ...overrides,
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/health", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true }) }));
  await page.route("**/api/kb/documents?collection=all", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/kb/wiki/coverage", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [], counts: { uncovered: 0, partial: 0, covered: 0, stale: 0 } }) }));
  await page.route("**/api/libraries", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      active_library_id: "library-1",
      libraries: [{ library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true }],
    }),
  }));
});



test("first upload creates a portable library before indexing the file", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  let created = false;
  let importLibraryHeader = "";
  const library = { library_id: "new-library", name: "算法资料", created_at: "", last_opened_at: "", active: true, available: true };
  await page.route("**/api/libraries", async (route) => {
    if (route.request().method() === "POST") {
      created = true;
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(library) });
    } else {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ active_library_id: created ? library.library_id : null, libraries: created ? [library] : [] }) });
    }
  });
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload({ workspace_name: "Bobodan", providers: [] })) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/kb/import", (route) => {
    importLibraryHeader = route.request().headers()["x-bobodan-library-id"] || "";
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ imported: ["lesson.md"], rejected: [], sync: {} }) });
  });

  await page.goto("/chat");
  const fileChooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "导入资料" }).click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.setFiles({ name: "lesson.md", mimeType: "text/markdown", buffer: Buffer.from("# Lesson") });
  await expect(page.getByRole("heading", { name: "准备导入 1 份资料" })).toBeVisible();
  await page.getByLabel("资料库名称").fill("算法资料");
  await page.getByLabel("保存到这个目录").fill("D:\\Learning");
  await page.getByRole("button", { name: "创建并继续导入" }).click();
  await expect(page.getByText("已导入 1 份资料并建立索引。")).toBeVisible();
  await expect(page).toHaveURL(/\/library/);
  expect(importLibraryHeader).toBe("new-library");
});




test("review reuses historical questions without regenerating them", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("bobodan:onboarding:v1", "complete");
    localStorage.setItem("bobodan:scope:documents", JSON.stringify(["unrelated-doc"]));
  });
  let generationCalled = false;
  let sessionBody: Record<string, unknown> = {};
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [{ concept: "RAG效果影响因素", status: "learning", question_ids: [5] }], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/quiz/questions", (route) => {
    generationCalled = true;
    return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: { message: "不应重新生成" } }) });
  });
  await page.route("**/api/quiz/sessions", async (route) => {
    sessionBody = route.request().postDataJSON();
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ practice_session_id: 12, question_ids: [5], questions: [] }) });
  });
  await page.route("**/api/quiz/sessions/12", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ practice_session_id: 12, status: "active", questions: [], attempts: [], progress: { answered: 0, total: 0, correct: 0, current_index: 0, completed: true } }) }));

  await page.goto("/review");
  await page.getByRole("button", { name: /开始复习/ }).click();
  await expect(page).toHaveURL(/\/practice\/12/);
  expect(generationCalled).toBe(false);
  expect(sessionBody.question_ids).toEqual([5]);
});





test("background Wiki planning restores from its persisted run", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const runId = "e".repeat(32);
  const planning = {
    run_id: runId,
    status: "planning",
    phase: "discovering",
    scope: { mode: "uncovered", document_ids: ["d1", "d2", "d3", "d4", "d5", "d6"], documents: ["一", "二", "三", "四", "五", "六"] },
    total_batches: 2,
    completed_batches: 1,
    completed_pages: 0,
    total_pages: 0,
  };
  const planned = {
    ...planning,
    plan_id: runId,
    status: "planned",
    phase: "planned",
    action: "generate",
    instruction: "",
    created_at: "2026-07-14T00:00:00Z",
    batches: [
      { batch_id: "b1", index: 1, document_ids: ["d1", "d2", "d3", "d4", "d5"], documents: ["一", "二", "三", "四", "五"], status: "planned" },
      { batch_id: "b2", index: 2, document_ids: ["d6"], documents: ["六"], status: "planned" },
    ],
    summary: { add: 6, update: 0, merge: 0, conflict: 0, skip: 0, split: 0 },
    changes: Array.from({ length: 6 }, (_, index) => ({
      change_id: `source-${index}`,
      kind: "add",
      title: `资料 ${index + 1}`,
      page_type: "wiki_source",
      summary: "资料摘要",
      related: [],
      source_count: 1,
      target: `sources/${index + 1}.md`,
      content: "## 摘要\n\n可追溯资料摘要。",
    })),
  };
  const artifact = { artifact_id: "run-artifact", type: "wiki_plan", operation: "generate", status: "cancelled", plan_id: runId, plan: planning };
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [{ chat_session_id: "run-session", name: "全库 Wiki", name_source: "ai", created_at: "", last_active: "", message_count: 2 }] }) }));
  await page.route("**/api/chat/sessions/run-session", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "run-session", name: "全库 Wiki", name_source: "ai", created_at: "", last_active: "", message_count: 2, messages: [{ role: "user", content: "/wiki plan" }, { role: "assistant", content: "正在规划。", artifacts: [artifact] }] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route(`**/api/kb/wiki/runs/${runId}`, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(planned) }));

  await page.goto("/chat/run-session");
  await expect(page.getByRole("region", { name: "Wiki 整理计划" })).toBeVisible();
  await expect(page.getByText("6 份资料 · 2 个批次")).toBeVisible();
  await expect(page.getByRole("button", { name: "确认并生成" })).toBeVisible();
});

test("cancelled Wiki session opens when the persisted run has no plan summary", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const runId = "f".repeat(32);
  const planning = {
    run_id: runId,
    status: "planning",
    phase: "cancelling",
    scope: { mode: "smart_library", document_ids: ["doc-1"], documents: ["资料 1"] },
    total_batches: 1,
    completed_batches: 0,
    completed_pages: 0,
    total_pages: 0,
  };
  const artifact = { artifact_id: "cancelled-artifact", type: "wiki_plan", operation: "generate", status: "cancelled", plan_id: runId, plan: planning };
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/chat/sessions/cancelled-session", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "cancelled-session", name: "已取消 Wiki", name_source: "fallback", created_at: "", last_active: "", message_count: 2, messages: [{ role: "user", content: "/wiki plan" }, { role: "assistant", content: "正在整理。", artifacts: [artifact] }] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route(`**/api/kb/wiki/runs/${runId}`, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...planning, status: "cancelled", phase: "cancelled", error: "Wiki run cancelled" }) }));

  await page.goto("/chat/cancelled-session");

  await expect(page.getByRole("region", { name: "已取消的 Wiki 整理计划" })).toBeVisible();
  await expect(page.getByText("本轮整理已取消")).toBeVisible();
});

test("staged Wiki plans explain the pause and offer a safe next step", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const planId = "c".repeat(32);
  const changes = [
    { change_id: "short-update", kind: "update", title: "大模型", page_type: "wiki_entity", summary: "更新概览", related: [], source_count: 4, target: "entities/大模型.md", content: "短草稿" },
    ...Array.from({ length: 5 }, (_, index) => ({ change_id: `new-${index}`, kind: "add", title: `新页面 ${index + 1}`, page_type: "wiki_concept", summary: "新增概念", related: [], source_count: 2, target: `concepts/new-${index}.md`, content: "可追溯正文" })),
  ];
  const stagedPlan = {
    plan_id: planId, status: "planned", action: "generate", instruction: "整理核心概念", created_at: "2026-07-14T00:00:00Z",
    scope: { document_ids: ["doc-1"], documents: ["大模型认知与工程概览"] },
    summary: { add: 5, update: 1, merge: 0, conflict: 0, skip: 0 }, changes,
    staging: [
      { change_id: "short-update", path: `${planId}/short-update.json`, errors: ["incoming body is unexpectedly shorter than the existing page"] },
      { change_id: "short-update", path: `${planId}/short-update.json`, errors: ["incoming body is unexpectedly shorter than the existing page"] },
    ],
  };
  const resultArtifact = { artifact_id: "wiki-recovery-result", type: "wiki_result", operation: "apply", status: "applied", plan_id: planId, checkpoint_id: "d".repeat(32), written: Array.from({ length: 5 }, (_, index) => `concepts/new-${index}.md`), kept_existing: ["大模型"] };
  let recovered = false;
  const messages = () => [
    { role: "user", content: "/wiki plan 整理核心概念" },
    { role: "assistant", content: "已生成 Wiki 计划。", artifacts: [{ artifact_id: "staged-plan", type: "wiki_plan", operation: "generate", status: recovered ? "applied" : "planned", plan_id: planId, plan: recovered ? { ...stagedPlan, status: "applied", staging: undefined, written: resultArtifact.written } : stagedPlan }] },
    ...(recovered ? [{ role: "assistant", content: "已保留问题页面的原内容，并生成其余可安全写入的 Wiki 页面。", artifacts: [resultArtifact] }] : []),
  ];
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [{ chat_session_id: "wiki-recovery", name: "Wiki 整理", name_source: "ai", created_at: "", last_active: "", message_count: messages().length }] }) }));
  await page.route("**/api/chat/sessions/wiki-recovery", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "wiki-recovery", name: "Wiki 整理", name_source: "ai", created_at: "", last_active: "", message_count: messages().length, messages: messages() }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route(`**/api/chat/wiki/plans/${planId}/recover`, async (route) => {
    expect(route.request().postDataJSON().strategy).toBe("keep_existing");
    recovered = true;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "wiki-recovery", artifact: resultArtifact }) });
  });

  await page.goto("/chat/wiki-recovery");
  await expect(page.getByText("1 个页面需要你选择处理方式")).toBeVisible();
  await expect(page.getByText("现有 Wiki 没有被修改", { exact: false })).toBeVisible();
  await expect(page.getByText("新草稿比现有页面短", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "补全后重新规划" })).toBeVisible();
  await page.getByRole("button", { name: "保留原页，生成其余 5 页" }).click();
  await expect(page.getByText("已保留“大模型”的原页面，并写入其余 5 个页面。")).toBeVisible();
});


test("confirmed web research keeps source selection explicit and traceable", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));

  const candidate = { candidate_id: "candidate-1", title: "Official guide", url: "https://example.com/guide", domain: "example.com", snippet: "Search preview only", published_at: null, rank: 1, provider: "exa", quality_hint: "reference" };
  const candidatesArtifact: any = { type: "web_candidates", artifact_id: "web-candidates-1", search_id: "search-1", status: "ready", query: "RAG 最新资料", provider: "exa", candidates: [candidate] };
  const evidenceArtifact = { type: "web_evidence", artifact_id: "web-evidence-1", research_id: "research-1", status: "ready", failed_source_ids: [], sources: [{ source_type: "web", source_id: "snapshot-1", snapshot_id: "snapshot-1", title: "Official guide", url: "https://example.com/guide", domain: "example.com", accessed_at: "2026-07-14T00:00:00Z", reader: "direct" }] };
  let messages: any[] = [];
  let runBody: Record<string, any> = {};

  await page.route("**/api/chat/web/searches", async (route) => {
    messages = [{ role: "user", content: "RAG 最新资料" }, { role: "assistant", content: "已整理联网候选来源，请选择需要读取的网页。", artifacts: [candidatesArtifact] }];
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "web-session", artifact: candidatesArtifact }) });
  });
  await page.route("**/api/chat/web/searches/search-1/select", async (route) => {
    candidatesArtifact.status = "used";
    messages.push({ role: "assistant", content: "选中的网页证据已经准备好，可以继续回答。", artifacts: [evidenceArtifact] });
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "web-session", artifact: evidenceArtifact }) });
  });
  await page.route("**/api/chat/web/sources/snapshot-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ source: { id: "snapshot-1", final_url: "https://example.com/guide", title: "Official guide", domain: "example.com", excerpt: "当时保存的可核实引用片段。", accessed_at: "2026-07-14T00:00:00Z", reader: "direct" } }) }));
  await page.route("**/api/chat/sessions/web-session", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "web-session", name: "网页研究", name_source: "fallback", created_at: "", last_active: "", message_count: messages.length, provider_name: "deepseek", messages }) }));
  await page.route("**/api/chat/runs", async (route) => {
    runBody = route.request().postDataJSON();
    await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream; charset=utf-8" }, body: `event: run_started\ndata: {"run_id":"web-run","chat_session_id":"web-session"}\n\nevent: citation\ndata: {"attribution":{"kind":"web","sources":[{"source_type":"web","source_id":"snapshot-1","snapshot_id":"snapshot-1","title":"Official guide","url":"https://example.com/guide","domain":"example.com","accessed_at":"2026-07-14T00:00:00Z","reader":"direct"}]}}\n\nevent: message_delta\ndata: {"content":"这是基于已选网页证据的回答。"}\n\nevent: run_completed\ndata: {"chat_session_id":"web-session","termination_reason":"final_answer"}\n\n` });
  });
  await page.route("**/api/chat/sessions/web-session/title", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ name: "网页研究", name_source: "ai" }) }));

  await page.goto("/chat");
  await page.getByRole("button", { name: "本轮搜索网页候选" }).click();
  await page.getByLabel("消息").fill("RAG 最新资料");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("checkbox", { name: /Official guide/ })).not.toBeChecked();
  await page.getByRole("checkbox", { name: /Official guide/ }).check();
  await page.getByRole("button", { name: "使用选中来源" }).click();
  await expect(page.getByText("这是基于已选网页证据的回答。")).toBeVisible();
  expect(runBody.web_research_id).toBe("research-1");
  await expect(page.locator(".source-chip.web")).toContainText("网页来源");
  await page.locator(".source-chip.web").click();
  await expect(page.getByText("当时保存的可核实引用片段。" )).toBeVisible();
});

test("slash palette exposes commands and local skills", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const skills = [{ name: "study-loop", description: "推进每日学习闭环。", enabled: true, source: "built-in", capabilities: ["学习对话"] }, { name: "exam-prep", description: "围绕薄弱点集中复习。", enabled: true, source: "built-in", capabilities: ["学习对话"] }];
  const skillSettings = settingsPayload({ skills });
  skillSettings.preferences.skills.enabled_names = skills.map((skill) => skill.name);
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(skillSettings) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  let requestBody: Record<string, unknown> = {};
  await page.route("**/api/chat/runs", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream; charset=utf-8" }, body: `event: run_started\ndata: {"run_id":"skill-run","chat_session_id":"skill-session"}\n\nevent: message_delta\ndata: {"content":"已按学习闭环整理。"}\n\nevent: run_completed\ndata: {"chat_session_id":"skill-session","termination_reason":"final_answer"}\n\n` });
  });
  await page.route("**/api/chat/sessions/skill-session", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "skill-session", name: "学习闭环", name_source: "ai", created_at: "2026-07-11T10:00:00", last_active: "2026-07-11T10:00:00", message_count: 2, messages: [{ role: "user", content: "/skill study-loop 整理今天的学习任务" }, { role: "assistant", content: "已按学习闭环整理。" }] }) }));
  await page.route("**/api/chat/sessions/skill-session/title", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ name: "学习闭环", name_source: "ai" }) }));

  await page.goto("/chat");
  const composer = page.getByRole("textbox", { name: "消息" });
  await composer.fill("/");
  await expect(page.getByRole("listbox", { name: "命令与技能" })).toBeVisible();
  expect(await composer.evaluate((element) => element.getBoundingClientRect().bottom < window.innerHeight - 55)).toBe(true);
  await expect(page.getByRole("option", { name: /^\/wiki 打开 Wiki/ })).toBeVisible();
  await composer.fill("/skill");
  await expect(page.getByRole("option", { name: /study-loop/ })).toBeVisible();
  await composer.press("ArrowDown");
  await composer.press("Enter");
  await expect(composer).toHaveValue(/\/skill (study-loop|exam-prep) /);
  const selectedSkill = await composer.inputValue();
  await composer.fill(`${selectedSkill}整理今天的学习任务`);
  await composer.press("Enter");
  await expect(page.getByText("已按学习闭环整理。")).toBeVisible();
  expect(String(requestBody.message)).toContain("/skill ");
  const activeComposer = page.getByRole("textbox", { name: "消息" });
  await activeComposer.fill("/wiki");
  await page.getByRole("option", { name: /^\/wiki 打开 Wiki/ }).click();
  await activeComposer.press("Enter");
  await expect(page).toHaveURL(/\/library\?collection=wiki/);
});

test("chat answer becomes practice and returns to review", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const question = { id: 41, type: "single_choice", type_label: "单选", question: "Dijkstra 使用哪种策略？", options: ["A. 分治", "B. 贪心", "C. 回溯", "D. 穷举"], concepts: ["Dijkstra"], difficulty: "easy", attribution: { kind: "local", sources: [] } };
  let completed = false;
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [{ chat_session_id: "demo", name: "Dijkstra", name_source: "ai", created_at: "2026-07-11T10:00:00", last_active: "2026-07-11T10:00:00", message_count: 2 }] }) }));
  await page.route("**/api/chat/sessions/demo", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "demo", name: "Dijkstra", name_source: "ai", created_at: "2026-07-11T10:00:00", last_active: "2026-07-11T10:00:00", message_count: 2, messages: [{ role: "user", content: "Dijkstra 为什么使用贪心？" }, { role: "assistant", content: "因为非负权保证已确定距离不会被推翻。" }] }) }));
  await page.route("**/api/chat/runs", (route) => route.fulfill({
    status: 200,
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    body: `event: run_started\ndata: {"run_id":"hint","chat_session_id":"hint-session"}\n\nevent: message_delta\ndata: {"content":"先想一想：当前最短距离确定后，什么条件保证它不会再变小？"}\n\nevent: run_completed\ndata: {"chat_session_id":"hint-session","termination_reason":"final_answer"}\n\n`,
  }));
  await page.route("**/api/chat/sessions/hint-session/title", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ name: "Dijkstra 题目提示", name_source: "ai" }) }));
  await page.route("**/api/quiz/questions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ question_ids: [41], questions: [question] }) }));
  await page.route("**/api/quiz/sessions", async (route) => {
    if (route.request().method() === "POST") await route.fulfill({ contentType: "application/json", body: JSON.stringify({ practice_session_id: 7, questions: [question] }) });
    else await route.fallback();
  });
  await page.route("**/api/quiz/sessions/active", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/quiz/sessions/7", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ practice_session_id: 7, status: completed ? "completed" : "active", questions: [question], attempts: [], progress: { answered: completed ? 1 : 0, total: 1, correct: completed ? 1 : 0, current_index: 0, completed } }) }));
  await page.route("**/api/quiz/answers", (route) => {
    completed = true;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ is_correct: true, feedback: "理解正确", correct_answer: "B", explanation: "每一步选择当前最短距离。", mastery_changes: [], progress: { answered: 1, total: 1, correct: 1, current_index: 0, completed: true }, session_completed: true }) });
  });
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [{ concept: "Dijkstra" }], wrong_answers: [], weaknesses: [] }) }));

  await page.goto("/chat/demo");
  await page.getByRole("button", { name: /生成 5 道练习/ }).click();
  await expect(page.getByRole("heading", { name: "开始一轮练习" })).toBeVisible();
  await page.getByRole("button", { name: /生成 5 题/ }).click();
  await expect(page).toHaveURL(/\/practice\/7/);
  await page.getByRole("button", { name: "问 AI" }).click();
  await expect(page.getByRole("dialog", { name: "问 Bobodan" })).toBeVisible();
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText(/先想一想：当前最短距离确定后/)).toBeVisible();
  await expect(page).toHaveURL(/\/practice\/7/);
  await page.getByRole("button", { name: "关闭问 AI" }).click();
  await page.getByText("B. 贪心", { exact: true }).click();
  await page.getByRole("button", { name: /提交答案/ }).click();
  await expect(page.getByText("答对了")).toBeVisible();
  await page.getByRole("button", { name: /查看小结/ }).click();
  await expect(page.getByText("这一轮练习已完成")).toBeVisible();
  await page.getByRole("button", { name: /查看复习建议/ }).click();
  await expect(page.getByRole("heading", { name: "今天的复习" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dijkstra", level: 3 })).toBeVisible();
});

test("chat question generation shows Bobodan process and opens prepared practice", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const question = { id: 51, type: "true_false", type_label: "判断", question: "LangChain 是否使用 Runnable 抽象？", options: [], concepts: ["LangChain"], difficulty: "easy", attribution: { kind: "local_extension", sources: [] } };
  const artifact = { type: "practice_ready", artifact_id: "practice-ready-1", status: "ready", topic: "LangChain", question_ids: [51], count: 1, attribution: { kind: "local_extension", sources: [] } };
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/chat/runs", (route) => route.fulfill({
    status: 200,
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    body: `event: run_started\ndata: {"run_id":"practice-run","chat_session_id":"practice-chat"}\n\nevent: status\ndata: {"phase":"running","message":"正在生成练习题","tool_name":"question_generate"}\n\nevent: chat_artifact\ndata: {"artifact":${JSON.stringify(artifact)}}\n\nevent: message_delta\ndata: {"content":"题目已经准备好，开始练习吧。"}\n\n`,
  }));
  await page.route("**/api/chat/sessions/practice-chat/title", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ name: "LangChain 练习", name_source: "ai" }) }));
  await page.route("**/api/chat/sessions/practice-chat", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "practice-chat", name: "LangChain 练习", name_source: "ai", created_at: "", last_active: "", message_count: 2, provider_name: "deepseek", messages: [{ role: "user", content: "帮我生成 LangChain 练习题" }, { role: "assistant", content: "题目已经准备好，开始练习吧。", artifacts: [artifact] }] }) }));
  await page.route("**/api/chat/practice/practice-ready-1/start", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "practice-chat", artifact: { ...artifact, status: "started", practice_session_id: 9 }, practice_session_id: 9 }) }));
  await page.route("**/api/quiz/sessions/9", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ practice_session_id: 9, status: "active", questions: [question], attempts: [], progress: { answered: 0, total: 1, correct: 0, current_index: 0, completed: false } }) }));

  await page.goto("/chat");
  await page.getByRole("textbox", { name: "消息" }).fill("帮我生成 LangChain 练习题");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.locator('.bobodan-process img[src*="bobodan-state-writing"]')).toBeVisible();
  await expect(page.locator(".bobodan-process-ink i")).toHaveCount(3);
  const processAnimation = await page.evaluate(() => {
    for (const styleSheet of Array.from(document.styleSheets)) {
      for (const rule of Array.from(styleSheet.cssRules)) {
        if (rule instanceof CSSStyleRule && rule.selectorText === ".bobodan-process-ink i") return rule.style.animation;
      }
    }
    return "";
  });
  expect(processAnimation).toContain("process-ink");
  await expect(page.getByText("1 道题已经准备好")).toBeVisible();
  await page.getByRole("button", { name: "开始练习" }).click();
  await expect(page).toHaveURL(/\/practice\/9/);
  await expect(page.getByText("LangChain 是否使用 Runnable 抽象？")).toBeVisible();
});

test("true-false practice uses explicit choices and submits a normalized answer", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const question = { id: 71, type: "true_false", type_label: "判断", question: "RAG 中资料越多，检索效果一定越好。", options: [], concepts: ["RAG"], difficulty: "medium", attribution: { kind: "local_extension", sources: [] } };
  let submittedAnswer = "";
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/quiz/sessions/12", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ practice_session_id: 12, status: "active", questions: [question], attempts: [], progress: { answered: 0, total: 1, correct: 0, current_index: 0, completed: false } }) }));
  await page.route("**/api/quiz/answers", async (route) => {
    submittedAnswer = route.request().postDataJSON().answer;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ is_correct: true, feedback: "正确", correct_answer: "false", explanation: "资料质量比数量更重要。", mastery_changes: [], progress: { answered: 1, total: 1, correct: 1, current_index: 0, completed: true }, session_completed: true }) });
  });

  await page.goto("/practice/12");
  await expect(page.getByText("判断题 · 中等难度")).toBeVisible();
  await expect(page.getByRole("radio", { name: /正确/ })).toBeVisible();
  await expect(page.getByRole("radio", { name: /错误/ })).toBeVisible();
  await expect(page.locator(".short-answer")).toHaveCount(0);
  await page.getByText("错误", { exact: true }).click();
  await expect(page.getByRole("radio", { name: /错误/ })).toBeChecked();
  await page.getByRole("button", { name: /提交答案/ }).click();
  expect(submittedAnswer).toBe("false");
});

test("reduced motion preserves toggle state and Skills controls stay readable", async ({ page }, testInfo) => {
  // Mobile device emulation (isMobile + 100dvh full-screen dialog) makes the
  // full-screen settings sheet's lower half un-clickable in the emulator
  // (elementFromPoint returns null inside the layout viewport). The toggle
  // behavior itself is viewport-independent: desktop/narrow run it, the
  // backend PATCH /api/settings/preferences contract covers the write.
  test.skip(testInfo.project.name === "mobile", "mobile emulation cannot click inside the 100dvh settings sheet");
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const currentSettings: any = settingsPayload({
    skills: [
      { name: "course-learning", description: "Use RAG and knowledge graph tools to answer course-learning questions with sources and related concepts.", source: "built-in", capabilities: ["学习对话", "资料理解"], enabled: true },
      { name: "exam-prep", description: "考前复习和薄弱点训练模式。", source: "built-in", capabilities: ["学习对话", "资料理解"], enabled: true },
    ],
  });
  currentSettings.preferences.appearance.motion = "reduced";
  currentSettings.preferences.skills.enabled_names = ["course-learning", "exam-prep"];
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(currentSettings) }));
  await page.route("**/api/settings/preferences", async (route) => {
    const patch = route.request().postDataJSON().patch;
    for (const [group, values] of Object.entries(patch)) {
      currentSettings.preferences[group] = { ...currentSettings.preferences[group], ...(values as Record<string, unknown>) };
    }
    currentSettings.preferences.revision += 1;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ preferences: currentSettings.preferences }) });
  });
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));

  await page.goto("/chat?settings=skills");
  const skillsDialog = page.getByRole("dialog", { name: "设置" });
  await expect(skillsDialog.getByText(/能力：学习对话、资料理解/).first()).toBeVisible();
  await expect(skillsDialog.getByRole("switch", { name: "course-learning 技能" })).toHaveAttribute("aria-checked", "true");

  await skillsDialog.getByRole("button", { name: "界面与阅读" }).click();
  const paperToggle = skillsDialog.getByRole("switch", { name: "纸张纹理" });
  await expect(paperToggle).toHaveAttribute("aria-checked", "true");
  expect(await paperToggle.locator("i").evaluate((element) => getComputedStyle(element).transform)).not.toBe("none");
  const motionToggle = skillsDialog.getByRole("switch", { name: "减少动态效果" });
  await motionToggle.click();
  await expect(motionToggle).toHaveAttribute("aria-checked", "false");
});

test("practice asks before web fallback and keeps the topic", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const question = { id: 61, type: "true_false", type_label: "判断", question: "LangChain 是 LLM 应用框架吗？", options: [], concepts: ["LangChain"], difficulty: "easy", attribution: { kind: "web", sources: [] } };
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/quiz/sessions/active", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/quiz/questions", (route) => {
    const body = route.request().postDataJSON();
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(body.web_confirmed
      ? { status: "ready", question_ids: [61], questions: [question], resolved_query: "LangChain", web_research_id: "research-61" }
      : { status: "web_consent_required", query: "LangChain", suggested_query: "LangChain", reason: "当前资料库中没有足够的相关内容。" }) });
  });
  await page.route("**/api/quiz/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ practice_session_id: 10, questions: [question] }) }));
  await page.route("**/api/quiz/sessions/10", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ practice_session_id: 10, status: "active", questions: [question], attempts: [], progress: { answered: 0, total: 1, correct: 0, current_index: 0, completed: false } }) }));

  await page.goto("/practice");
  await page.getByLabel("想练习什么？").fill("langchian");
  await page.getByRole("button", { name: "生成 5 题" }).click();
  await expect(page.getByText("本地资料暂时不足")).toBeVisible();
  await expect(page.getByText(/建议按“LangChain”/)).toBeVisible();
  await page.getByRole("button", { name: "联网找资料出题" }).click();
  await expect(page).toHaveURL(/\/practice\/10/);
  await expect(page.getByText(/已将“langchian”按“LangChain”理解/)).toBeVisible();
});


