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

test("personal knowledge is managed from settings with confirmation", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  let candidates = [{
    id: "candidate-1", scope: "library", kind: "learning_strategy", operation: "create",
    title: "复习方式", content: "先主动回忆，再查看答案", target_item_id: null,
    confidence: .8, reason: "学习对话中多次出现", evidence: [{ excerpt: "我想先自己回忆" }],
    status: "pending", created_at: "2026-07-14T10:00:00Z", updated_at: "2026-07-14T10:00:00Z",
  }];
  let knowledge = [{
    id: "knowledge-1", scope: "global", kind: "preference", title: "讲解偏好",
    content: "先给直觉，再给严格定义", pinned: true, confidence: 1, evidence: [],
    created_at: "2026-07-13T10:00:00Z", updated_at: "2026-07-14T09:00:00Z", revision: 1,
  }];
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [], personalization: [] }) }));
  await page.route("**/api/memory/overview", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ knowledge_count: knowledge.length, global_count: 1, library_count: 0, pending_candidate_count: candidates.length, event_count: 1, jobs: { pending: 0, failed: 0 } }) }));
  await page.route("**/api/memory/knowledge?scope=all&query=", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: knowledge }) }));
  await page.route("**/api/memory/candidates", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ candidates }) }));
  await page.route("**/api/memory/events?limit=200", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ events: [{ id: "event-1", type: "practice_completed", source_type: "quiz", source_id: "7", payload: { correct: 4 }, occurred_at: "2026-07-14T11:00:00Z" }] }) }));
  await page.route("**/api/memory/candidates/candidate-1/confirm", (route) => {
    const item = { ...knowledge[0], id: "knowledge-2", scope: "library", kind: "learning_strategy", title: candidates[0].title, content: candidates[0].content, pinned: false };
    knowledge = [...knowledge, item];
    candidates = [];
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ item, candidate: { id: "candidate-1", status: "confirmed" } }) });
  });

  await page.goto("/chat?settings=memory");
  await expect(page.getByRole("heading", { name: "记忆与数据" }).last()).toBeVisible();
  await page.getByRole("button", { name: /管理个人知识/ }).click();
  await expect(page.getByRole("heading", { name: "管理个人知识" })).toBeVisible();
  await expect(page.getByText("讲解偏好")).toBeVisible();
  await page.getByRole("button", { name: /待确认/ }).click();
  await expect(page.getByText("复习方式")).toBeVisible();
  await page.getByText("查看证据与编辑").click();
  await expect(page.getByRole("textbox", { name: "内容" })).toHaveValue("先主动回忆，再查看答案");
  await page.getByRole("button", { name: "确认并保存" }).click();
  await expect(page.getByText("目前没有等待确认的知识候选。")).toBeVisible();
});

test("new workspace completes the four-step setup", async ({ page }) => {
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload({ workspace_name: "新学习空间" })) }));

  await page.goto("/chat");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("怎么称呼你").fill("小科");
  await page.getByLabel("最近最想完成的学习目标").fill("掌握图算法");
  await page.getByRole("button", { name: /下一步/ }).click();
  await expect(page.getByRole("heading", { name: "AI 连接" })).toBeVisible();
  await page.getByRole("button", { name: /下一步/ }).click();
  await expect(page.getByRole("heading", { name: "学习空间" })).toBeVisible();
  await page.getByRole("button", { name: /下一步/ }).click();
  await expect(page.getByRole("heading", { name: "边界" })).toBeVisible();
  await page.getByRole("button", { name: /开始学习/ }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  expect(await page.evaluate(() => localStorage.getItem("bobodan:onboarding:v1"))).toBe("complete");
  expect(await page.evaluate(() => localStorage.getItem("bobodan:learning-profile"))).toContain("掌握图算法");
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

test("legacy folder is previewed and migrated from the Web UI", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  let migrated = false;
  const library = { library_id: "legacy-library", name: "旧课程资料", created_at: "", last_opened_at: "", active: true, available: true };
  await page.route("**/api/libraries", async (route) => {
    if (route.request().method() === "POST") {
      migrated = true;
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ library, preview: { material_count: 55 }, sync: { scanned_files: 55 } }) });
    } else {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ active_library_id: migrated ? library.library_id : null, libraries: migrated ? [library] : [] }) });
    }
  });
  await page.route("**/api/libraries/migrate/preview", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ folder_name: "vault", already_initialized: false, material_count: 55, size_bytes: 520_000_000, wiki_pages: 6, legacy_source_count: 1 }) }));
  await page.route("**/api/libraries/migrate", (route) => {
    migrated = true;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ library, preview: { material_count: 55 }, sync: { scanned_files: 55 } }) });
  });
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload({ workspace_name: "Bobodan", providers: [] })) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));

  await page.goto("/library");
  await page.getByRole("button", { name: "资料库管理" }).click();
  await page.getByRole("tab", { name: "接入旧文件夹" }).click();
  await page.getByLabel("资料库名称").fill("旧课程资料");
  await page.getByLabel("需要原地接入的资料文件夹").fill("F:\\project\\note\\vault");
  await page.getByRole("button", { name: "扫描文件夹" }).click();
  await expect(page.getByRole("region", { name: "接入扫描结果" })).toContainText("55 份可索引资料");
  await expect(page.getByRole("region", { name: "接入扫描结果" })).toContainText("6 个现有 Wiki 页面");
  await page.getByRole("button", { name: "确认原地接入" }).click();
  await expect(page).toHaveURL(/\/library/);
  await expect(page.locator(".profile-row strong")).toHaveText("旧课程资料");
});

test("initialized folder is opened instead of migrated again", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  let opened = false;
  let migrated = false;
  const library = { library_id: "existing-library", name: "已有资料库", created_at: "", last_opened_at: "", active: true, available: true };
  await page.route("**/api/libraries", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ active_library_id: opened ? library.library_id : null, libraries: opened ? [library] : [] }) }));
  await page.route("**/api/libraries/open", (route) => {
    opened = true;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(library) });
  });
  await page.route("**/api/libraries/migrate/preview", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ folder_name: "vault", already_initialized: true, material_count: 62, size_bytes: 520_000_000, wiki_pages: 7, legacy_source_count: 1 }) }));
  await page.route("**/api/libraries/migrate", (route) => {
    migrated = true;
    return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: { message: "不应再次迁移" } }) });
  });
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload({ workspace_name: "Bobodan", providers: [] })) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));

  await page.goto("/library");
  await page.getByRole("button", { name: "资料库管理" }).click();
  await page.getByRole("tab", { name: "接入旧文件夹" }).click();
  await page.getByLabel("需要原地接入的资料文件夹").fill("F:\\project\\note\\vault");
  await page.getByRole("button", { name: "扫描文件夹" }).click();
  await expect(page.getByRole("region", { name: "接入扫描结果" })).toContainText("这是一个 Bobodan 资料库");
  await page.getByRole("button", { name: "打开这个资料库" }).click();
  await expect(page.locator(".profile-row strong")).toHaveText("已有资料库");
  expect(opened).toBe(true);
  expect(migrated).toBe(false);
});

test("selected documents are preferred while chat still searches the whole library", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const documents = [{ document_id: "doc-1", source: "course/algorithm.md", kind: "course_document", title: "算法设计", collection: "material", content_role: "content", managed: false }];
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents }) }));
  await page.route("**/api/kb/documents/doc-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: documents[0], sections: [{ chunk_id: "c1", text: "Dijkstra 使用贪心策略。" }] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  let requestBody: Record<string, unknown> = {};
  await page.route("**/api/chat/runs", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
      body: `event: run_started\ndata: {"run_id":"r1","chat_session_id":"s1"}\n\nevent: message_delta\ndata: {"content":"回答"}\n\nevent: run_completed\ndata: {"chat_session_id":"s1","termination_reason":"final_answer"}\n\n`,
    });
  });
  await page.route("**/api/chat/sessions/s1/title", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ name: "范围问答", name_source: "ai" }) }));

  await page.goto("/library");
  await page.getByRole("button", { name: /设为优先资料 算法设计/ }).click();
  await page.locator(".reader-section-prose").selectText();
  await page.locator(".reader-prose").dispatchEvent("mouseup");
  await expect(page.getByRole("button", { name: "带到对话" })).toBeVisible();
  await page.goto("/chat");
  await expect(page.getByText("1 份优先资料")).toBeVisible();
  await page.getByRole("textbox", { name: "消息" }).fill("解释核心思路");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("回答", { exact: true })).toBeVisible();
  expect(requestBody.document_ids).toEqual([]);
  expect(requestBody.preferred_document_ids).toEqual(["doc-1"]);
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

test("Wiki maintenance separates checks from confirmed repairs", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const wikiDocument = { document_id: "wiki-1", source: "obsidian/wiki/sources/2026-07-17_RAG.md", kind: "wiki_source", title: "RAG", collection: "wiki", wiki_type: "source", content_role: "content", managed: false };
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/kb/documents?collection=wiki", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [wikiDocument] }) }));
  await page.route("**/api/kb/documents/wiki-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: wikiDocument, sections: [{ chunk_id: "w1", text: "RAG 是检索增强生成。" }] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/kb/wiki/maintenance", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ archived_count: 0, canonical_count: 7, plan_id: "r".repeat(32), health: { healthy: false, total_pages: 7, orphan_count: 1, broken_link_count: 0, missing_count: 0, stale_count: 0, vaults: [{ vault: "note/vault", total_pages: 7, orphans: ["旧页面"], broken_links: [], missing: [], stale: [], errors: [], healthy: false }] }, repair_plan: { plan_id: "r".repeat(32), status: "planned", health_snapshot: {}, items: [{ item_id: "repair-1", issue_type: "index_check", title: "重建 Wiki 页面索引", execution: "local", resolution: "reindex", status: "pending" }, { item_id: "repair-2", issue_type: "orphan", title: "旧页面", execution: "manual", resolution: "review", status: "pending" }] } }) });
    } else {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ healthy: false, total_pages: 7, orphan_count: 1, broken_link_count: 0, missing_count: 0, stale_count: 0, vaults: [{ vault: "note/vault", total_pages: 7, orphans: ["旧页面"], broken_links: [], missing: [], stale: [], errors: [], healthy: false }] }) });
    }
  });
  await page.route(`**/api/kb/wiki/repair-plans/${"r".repeat(32)}/apply`, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ plan_id: "r".repeat(32), status: "partial", health_snapshot: {}, applied_count: 1, pending_count: 1, items: [{ item_id: "repair-1", issue_type: "index_check", title: "重建 Wiki 页面索引", execution: "local", resolution: "reindex", status: "applied" }, { item_id: "repair-2", issue_type: "orphan", title: "旧页面", execution: "manual", resolution: "review", status: "pending" }] }) }));

  await page.goto("/library?collection=wiki");
  await expect(page.getByText("Wiki · 资料摘要")).toBeVisible();
  await page.getByRole("button", { name: "维护 Wiki" }).click();
  await expect(page.getByRole("region", { name: "Wiki 维护" })).toBeVisible();
  await expect(page.getByText("发现需要检查的结构问题")).toBeVisible();
  await page.getByText("查看问题详情").click();
  await expect(page.getByText(/孤立页：旧页面/)).toBeVisible();
  await page.getByRole("button", { name: "生成修复计划" }).click();
  await expect(page.getByRole("region", { name: "Wiki 修复计划" })).toBeVisible();
  await expect(page.getByText("重建 Wiki 页面索引")).toBeVisible();
  await page.getByRole("button", { name: "应用本地安全修复" }).click();
  await expect(page.getByText("已修复")).toBeVisible();
});

test("personal Wiki note restores its browser draft before explicit save", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  let createdBody: Record<string, unknown> | null = null;
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/kb/documents?collection=wiki", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/kb/wiki/pages", async (route) => {
    createdBody = route.request().postDataJSON();
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ page: { document_id: "note-1", title: "我的 RAG 笔记", collection: "wiki", wiki_type: "note" } }) });
  });

  await page.goto("/library?collection=wiki");
  await page.getByRole("button", { name: "新建笔记" }).click();
  await page.getByLabel("标题").fill("我的 RAG 笔记");
  await page.getByLabel("Markdown 正文").fill("## 关键点\n\n先检索，再生成。");
  await page.getByRole("button", { name: "关闭编辑器" }).click();
  await page.getByRole("button", { name: "新建笔记" }).click();
  await expect(page.getByLabel("标题")).toHaveValue("我的 RAG 笔记");
  await expect(page.getByLabel("Markdown 正文")).toHaveValue(/先检索，再生成/);
  await page.getByRole("button", { name: "预览" }).click();
  await expect(page.getByRole("heading", { name: "关键点" })).toBeVisible();
  await page.getByRole("button", { name: "保存页面" }).click();
  expect(createdBody).toMatchObject({ title: "我的 RAG 笔记", body: "## 关键点\n\n先检索，再生成。" });
  await expect(page.getByText("Wiki 页面已保存并重新建立索引。")).toBeVisible();
});

test("materials become a traceable Wiki only after plan confirmation", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const materials = Array.from({ length: 5 }, (_, index) => ({ document_id: `doc-${index + 1}`, source: `course/rag-${index + 1}.md`, kind: "course_document", title: `RAG Lesson ${index + 1}`, collection: "material", content_role: "content", managed: false }));
  const wiki = { document_id: "wiki-1", source: "obsidian/wiki/concepts/RAG.md", kind: "wiki_concept", title: "RAG", collection: "wiki", wiki_type: "concept", content_role: "content", managed: false };
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload({ workspace_name: "Study" })) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: materials }) }));
  await page.route("**/api/kb/documents?collection=wiki", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [wiki] }) }));
  await page.route("**/api/kb/documents/doc-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: materials[0], sections: [{ chunk_id: "chunk-1", heading: "Retrieval", page_start: 3, text: "RAG uses retrieved evidence." }] }) }));
  await page.route("**/api/kb/documents/wiki-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: wiki, sections: [{ chunk_id: "wiki-chunk", text: "RAG summary" }] }) }));
  const planned = {
    plan_id: "a".repeat(32), run_id: "a".repeat(32), status: "planned", phase: "planned", action: "generate", instruction: "", generation_mode: "standard",
    created_at: "2026-07-13T00:00:00Z",
    scope: { mode: "uncovered", document_ids: materials.map((item) => item.document_id), documents: materials.map((item) => item.title) },
    batches: [{ batch_id: "batch-1", index: 1, document_ids: materials.map((item) => item.document_id), documents: materials.map((item) => item.title), status: "planned" }],
    summary: { add: 1, update: 0, merge: 0, conflict: 0, skip: 0, split: 0 },
    changes: [{
      change_id: "change-1", kind: "add", title: "RAG", page_type: "wiki_concept",
      summary: "Grounded generation.", related: [], source_count: 1, target: "concepts/RAG.md",
      content: "## 原始资料\n\n- [RAG Lesson 1 · Retrieval](/library?collection=material&document=doc-1&chunk=chunk-1)",
    }],
  };
  await page.route("**/api/kb/wiki/coverage", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: materials.map((item) => ({ document_id: item.document_id, status: "uncovered", linked_page_count: 0, source_fingerprint: item.document_id })), counts: { uncovered: 5, partial: 0, covered: 0, stale: 0 } }) }));
  await page.route("**/api/kb/wiki/runs/estimate", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ generation_mode: "standard", document_count: 5, batch_count: 1, estimated_pages: [5, 11], request_range: [6, 22], input_token_range: [12000, 120000], output_token_range: [0, 33000], duration_range_seconds: [48, 990], rough: true, provider: "deepseek", model: "deepseek-chat" }) }));
  await page.route("**/api/kb/wiki/runs", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(planned) }));
  await page.route(`**/api/kb/wiki/plans/${planned.plan_id}/apply`, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...planned, status: "applied", checkpoint_id: "b".repeat(32), written: ["concepts/RAG.md"] }) }));

  await page.goto("/library");
  await expect(page.getByRole("region", { name: "Wiki 使用流程" })).toBeVisible();
  await page.getByRole("button", { name: /整理未覆盖资料 · 5/ }).click();
  await page.getByLabel("整理要求").fill("整理核心概念和证据");
  await page.getByRole("button", { name: "查看耗时与消耗" }).click();
  await expect(page.getByRole("region", { name: "Wiki 整理估算" })).toContainText("5");
  await expect(page.getByText(/消耗较多 Token/)).toBeVisible();
  await page.getByRole("button", { name: "确认并开始" }).click();
  await expect(page.getByRole("region", { name: "Wiki 整理计划" })).toBeVisible();
  await expect(page.getByText("先审查这份整理计划")).toBeVisible();
  await page.getByRole("button", { name: "确认并生成" }).click();
  await expect(page.getByText("Wiki 已按确认的计划写入，并重新建立本地索引。")).toBeVisible();
  await page.locator(".wiki-plan-change summary").click();
  await page.getByRole("link", { name: /RAG Lesson 1 · Retrieval/ }).click();
  await expect(page).toHaveURL(/collection=material&document=doc-1&chunk=chunk-1/);
  await expect(page.locator('[data-chunk-id="chunk-1"]')).toHaveClass(/highlighted/);
});

test("Library shows Wiki coverage and supports batch selection before smart planning", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const documents = Array.from({ length: 6 }, (_, index) => ({
    document_id: `doc-${index + 1}`,
    source: `raw/inbox/lesson-${index + 1}.md`,
    kind: "markdown",
    title: `资料 ${index + 1}`,
    course: index < 3 ? "课程 A" : "课程 B",
    collection: "material",
    content_role: "content",
    managed: false,
  }));
  const coverage = documents.map((document, index) => ({
    document_id: document.document_id,
    status: index === 4 ? "covered" : index === 5 ? "stale" : "uncovered",
    source_page_id: index === 4 ? "sources/资料 5.md" : null,
    linked_page_count: index === 4 ? 4 : index === 5 ? 2 : 0,
    source_fingerprint: `hash-${index}`,
    covered_at: index === 4 ? "2026-07-14" : null,
  }));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload()) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents }) }));
  await page.route("**/api/kb/documents/doc-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: documents[0], sections: [{ chunk_id: "c1", text: "课程资料内容" }] }) }));
  await page.route("**/api/kb/wiki/coverage", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: coverage, counts: { uncovered: 4, partial: 0, covered: 1, stale: 1 } }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));

  await page.goto("/library");
  await expect(page.getByRole("button", { name: /整理未覆盖资料 · 5/ })).toBeVisible();
  await expect(page.getByText("未整理 · 关联 0 页").first()).toBeVisible();
  await expect(page.getByText("原文已变化 · 关联 2 页")).toBeVisible();
  await page.getByRole("button", { name: "选择当前筛选" }).click();
  await expect(page.getByRole("button", { name: "清空 6" })).toBeVisible();
  await page.getByRole("button", { name: /整理未覆盖资料 · 5/ }).click();
  await expect(page.getByText(/将处理 5 份未覆盖或已变化资料/)).toBeVisible();
  await page.getByLabel("整理范围").selectOption("smart_library");
  await page.getByLabel("主题或目标").fill("Agent 与工具调用");
  await expect(page.getByText(/全库检索，并优先参考已选择的 6 份资料/)).toBeVisible();
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

test("settings deep links and @ references stay usable across viewports", async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const material = { document_id: "doc-material", source: "raw/inbox/rag.md", kind: "markdown", title: "RAG 原始资料", collection: "material", content_role: "content" };
  const wiki = { document_id: "doc-wiki", source: "wiki/concepts/RAG.md", kind: "wiki_concept", title: "RAG Wiki", collection: "wiki", content_role: "content", wiki_type: "concept" };
  const priorSession = { chat_session_id: "prior-session", name: "上次的 RAG 讨论", name_source: "ai", created_at: "2026-07-12T09:00:00", last_active: "2026-07-12T10:00:00", message_count: 2, provider_name: "deepseek" };
  const currentSettings = settingsPayload();
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(currentSettings) }));
  await page.route("**/api/settings/preferences", async (route) => {
    const body = route.request().postDataJSON();
    currentSettings.preferences = { ...currentSettings.preferences, ...body.patch, revision: currentSettings.preferences.revision + 1 };
    currentSettings.default_provider = currentSettings.preferences.ai.default_provider;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ preferences: currentSettings.preferences }) });
  });
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [priorSession] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [material] }) }));
  await page.route("**/api/kb/documents?collection=all", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [material, wiki] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  let requestBody: Record<string, any> = {};
  await page.route("**/api/chat/runs", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({ status: 200, headers: { "Content-Type": "text/event-stream; charset=utf-8" }, body: `event: run_started\ndata: {"run_id":"ref-run","chat_session_id":"ref-session"}\n\nevent: message_delta\ndata: {"content":"已结合引用回答。"}\n\nevent: run_completed\ndata: {"chat_session_id":"ref-session","termination_reason":"final_answer"}\n\n` });
  });
  await page.route("**/api/chat/sessions/ref-session/title", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ name: "引用问答", name_source: "ai" }) }));
  await page.route("**/api/chat/sessions/ref-session", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "ref-session", name: "引用问答", name_source: "ai", created_at: "", last_active: "", message_count: 2, provider_name: "deepseek", messages: [{ role: "user", content: "解释证据边界", references: [{ type: "document", id: "doc-wiki", title: "RAG Wiki", collection: "wiki" }] }, { role: "assistant", content: "已结合引用回答。" }] }) }));

  await page.goto("/chat?settings=appearance");
  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeLessThanOrEqual(await page.evaluate(() => window.innerWidth));
  await page.screenshot({ path: testInfo.outputPath(`settings-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });
  await page.getByPlaceholder("搜索设置").fill("模型");
  await page.getByPlaceholder("搜索设置").press("Enter");
  await expect(page.getByRole("heading", { name: "AI 与模型" }).last()).toBeVisible();
  const close = page.getByRole("button", { name: "关闭设置" });
  if (await close.isVisible()) await close.click();
  else await page.getByRole("button", { name: "返回" }).click();

  const composer = page.getByRole("textbox", { name: "消息" });
  await composer.fill("@资料");
  await expect(page.getByRole("listbox", { name: "引用资料或会话" })).toBeVisible();
  await page.getByRole("option", { name: /RAG Wiki/ }).click();
  await expect(page.getByRole("button", { name: "RAG Wiki", exact: true })).toBeVisible();
  await composer.fill("解释证据边界");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("已结合引用回答。", { exact: true })).toBeVisible();
  expect(requestBody.provider).toBe("deepseek");
  expect(requestBody.references).toEqual([{ type: "document", id: "doc-wiki", title: "RAG Wiki", collection: "wiki" }]);
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

test("reduced motion preserves toggle state and Skills controls stay readable", async ({ page }) => {
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

test("Chat and primary study routes render without overlap", async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(settingsPayload({ workspace_name: "本地工作区" })) }));
  const document = { document_id: "visual-doc", source: "course/visual.md", kind: "course_document", title: "视觉测试资料", collection: "material", content_role: "content", managed: false };
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [document] }) }));
  await page.route("**/api/kb/documents/visual-doc", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document, sections: [{ chunk_id: "visual-chunk", heading: "资料正文", text: "这是一段用于检查阅读字体、宽度和页面布局的本地资料。" }] }) }));
  await page.route("**/api/quiz/sessions/active", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [{ concept: "视觉测试知识点" }], wrong_answers: [], weaknesses: [] }) }));
  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: "今天想学点什么？", level: 2 })).toBeVisible();
  await expect(page.locator(".composer")).toBeVisible();
  await expect(page.locator(".composer-select.model.connected")).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.fonts.check('16px "Luo"'))).toBe(true);
  expect(await page.evaluate(() => getComputedStyle(document.body).fontFamily.startsWith("Luo"))).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`chat-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });

  await page.goto("/library");
  await expect(page.getByRole("heading", { name: "资料库", level: 2 })).toBeVisible();
  await expect(page.getByRole("tab", { name: "学习资料" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".document-row").first()).toBeVisible();
  await expect(page.locator(".reader-prose")).toBeVisible();
  expect(await page.locator(".reader-prose").evaluate((element) => getComputedStyle(element).fontFamily)).toContain("TsangerJinKai02");
  await expect.poll(
    () => page.evaluate(async () => (await document.fonts.load('16px "TsangerJinKai02"', "资料文章龘")).length),
    { timeout: 15_000 },
  ).toBeGreaterThan(0);
  await page.screenshot({ path: testInfo.outputPath(`library-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });

  await page.goto("/practice");
  await expect(page.getByRole("heading", { name: "开始一轮练习", level: 2 })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath(`practice-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });

  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "今天的复习", level: 2 })).toBeVisible();
  await expect(page.locator(".review-kind").first()).toBeVisible();
  expect(await page.locator(".review-kind").first().evaluate((element) => getComputedStyle(element).fontFamily)).toContain("Luo");
  expect(await page.locator(".context-content").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`review-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });
});

test("desktop sidebars collapse independently and persist", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/chat");
  await page.getByRole("button", { name: "收起左栏" }).click();
  await expect(page.locator(".app-shell")).toHaveClass(/left-collapsed/);
  expect(await page.evaluate(() => localStorage.getItem("bobodan:sidebar:left"))).toBe("false");
  await page.getByRole("button", { name: "收起右栏" }).click();
  await expect(page.locator(".app-shell")).toHaveClass(/right-collapsed/);
  await page.reload();
  await expect(page.locator(".app-shell")).toHaveClass(/left-collapsed/);
  await expect(page.locator(".app-shell")).toHaveClass(/right-collapsed/);
});

test("streamed conversation keeps a calm centered reading flow", async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/kb/documents?collection=material", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ documents: [{
        document_id: "doc-1",
        source: "course/algorithm.md",
        kind: "course_document",
        title: "算法设计",
        managed: false,
        origin: "workspace",
        collection: "material",
        content_role: "content",
      }] }),
    });
  });
  await page.route("**/api/kb/documents/doc-1", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        document: { document_id: "doc-1", source: "course/algorithm.md", kind: "course_document", title: "算法设计", collection: "material", content_role: "content" },
        sections: [{ chunk_id: "chunk-1", heading: "最短路径", page_start: 18, text: "非负权保证已确定的最短距离不会被后来推翻。" }],
      }),
    });
  });
  await page.route("**/api/chat/sessions/demo-session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        chat_session_id: "demo-session",
        name: "Dijkstra 的贪心选择",
        name_source: "ai",
        created_at: "2026-07-11T10:00:00",
        last_active: "2026-07-11T10:00:00",
        message_count: 0,
        messages: [],
      }),
    });
  });
  await page.route("**/api/chat/runs", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const frames = [
      ["run_started", { run_id: "run-1", chat_session_id: "demo-session" }],
      ["status", { phase: "running", message: "正在查找你的资料" }],
      ["message_delta", { content: "关键在于 **非负权** 保证已经确定的最短距离不会被后来推翻。\n\n当当前节点的暂定距离最小时，任何经过其他未确定节点再回到它的路径都不会更短。" }],
      ["citation", { attribution: { kind: "local", sources: [{ source_type: "local", source_id: "chunk-1", title: "算法设计", document_id: "doc-1", chunk_id: "chunk-1", page: 18 }] } }],
      ["run_completed", { chat_session_id: "demo-session", termination_reason: "final_answer" }],
    ];
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
      body: frames.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(""),
    });
  });
  await page.route("**/api/chat/sessions/demo-session/title", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ name: "Dijkstra 的贪心正确性", name_source: "ai" }) });
  });

  await page.goto("/chat/demo-session");
  await page.getByRole("textbox", { name: "消息" }).fill("Dijkstra 为什么可以使用贪心选择？");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("正在理解问题", { exact: true })).toBeVisible();
  await expect(page.getByText(/关键在于/)).toBeVisible();
  await expect(page.getByText(/本地资料 · 算法设计/)).toBeVisible();
  await expect(page.getByText("查看处理过程")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`conversation-${testInfo.project.name}.png`), fullPage: true, animations: "disabled" });

  await page.getByRole("link", { name: /本地资料 · 算法设计/ }).click();
  await expect(page).toHaveURL(/\/library\?collection=material&document=doc-1&chunk=chunk-1/);
  await expect(page.getByRole("heading", { name: "算法设计", level: 2 })).toBeVisible();
  await expect(page.locator('[data-chunk-id="chunk-1"]')).toHaveClass(/highlighted/);
});
