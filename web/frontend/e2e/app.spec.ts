import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/libraries", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      active_library_id: "library-1",
      libraries: [{ library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true }],
    }),
  }));
});

test("new workspace completes the four-step setup", async ({ page }) => {
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "新学习空间", default_provider: "deepseek", providers: [{ name: "deepseek", configured: true }], mcp_enabled: false }) }));

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
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "Bobodan", default_provider: "deepseek", providers: [], mcp_enabled: false, skills: [] }) }));
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
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "Bobodan", default_provider: "deepseek", providers: [], mcp_enabled: false, skills: [] }) }));
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
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "Bobodan", default_provider: "deepseek", providers: [], mcp_enabled: false, skills: [] }) }));
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

test("selected library scope is sent with chat requests", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const documents = [{ document_id: "doc-1", source: "course/algorithm.md", kind: "course_document", title: "算法设计", collection: "material", content_role: "content", managed: false }];
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents }) }));
  await page.route("**/api/kb/documents/doc-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: documents[0], sections: [{ chunk_id: "c1", text: "Dijkstra 使用贪心策略。" }] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "测试空间", default_provider: "deepseek", providers: [{ name: "deepseek", configured: true }], mcp_enabled: false }) }));
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
  await page.getByRole("button", { name: /加入学习范围 算法设计/ }).click();
  await page.locator(".reader-section-prose").selectText();
  await page.locator(".reader-prose").dispatchEvent("mouseup");
  await expect(page.getByRole("button", { name: "带到对话" })).toBeVisible();
  await page.goto("/chat");
  await expect(page.getByText("1 份资料")).toBeVisible();
  await page.getByRole("textbox", { name: "消息" }).fill("解释核心思路");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("回答", { exact: true })).toBeVisible();
  expect(requestBody.document_ids).toEqual(["doc-1"]);
});

test("review reuses historical questions without regenerating them", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("bobodan:onboarding:v1", "complete");
    localStorage.setItem("bobodan:scope:documents", JSON.stringify(["unrelated-doc"]));
  });
  let generationCalled = false;
  let sessionBody: Record<string, unknown> = {};
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "测试空间", default_provider: "deepseek", providers: [{ name: "deepseek", configured: true }], mcp_enabled: false }) }));
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

test("Wiki maintenance checks health and organizes generated pages", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  const wikiDocument = { document_id: "wiki-1", source: "obsidian/wiki/concepts/RAG.md", kind: "wiki_concept", title: "RAG", collection: "wiki", wiki_type: "concept", content_role: "content", managed: false };
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "测试空间", default_provider: "deepseek", providers: [{ name: "deepseek", configured: true }], mcp_enabled: false, skills: [] }) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [] }) }));
  await page.route("**/api/kb/documents?collection=wiki", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [wikiDocument] }) }));
  await page.route("**/api/kb/documents/wiki-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: wikiDocument, sections: [{ chunk_id: "w1", text: "RAG 是检索增强生成。" }] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/kb/wiki/maintenance", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ archived_count: 1, canonical_count: 6, health: { healthy: true, total_pages: 6, orphan_count: 0, broken_link_count: 0, missing_count: 0, stale_count: 0, vaults: [{ vault: "note/vault", total_pages: 6, orphans: [], broken_links: [], missing: [], stale: [], errors: [], healthy: true }] } }) });
    } else {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ healthy: false, total_pages: 7, orphan_count: 1, broken_link_count: 0, missing_count: 0, stale_count: 0, vaults: [{ vault: "note/vault", total_pages: 7, orphans: ["旧页面"], broken_links: [], missing: [], stale: [], errors: [], healthy: false }] }) });
    }
  });

  await page.goto("/library?collection=wiki");
  await page.getByRole("button", { name: "维护 Wiki" }).click();
  await expect(page.getByRole("region", { name: "Wiki 维护" })).toBeVisible();
  await expect(page.getByText("发现需要检查的结构问题")).toBeVisible();
  await page.getByText("查看问题详情").click();
  await expect(page.getByText(/孤立页：旧页面/)).toBeVisible();
  await page.getByRole("button", { name: "整理并重建索引" }).click();
  await expect(page.getByText("已生成 Wiki 修复预览；确认前不会改动任何页面。")).toBeVisible();
  await expect(page.getByText("Wiki 结构正常")).toBeVisible();
});

test("materials become a traceable Wiki only after plan confirmation", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("bobodan:onboarding:v1", "complete");
    localStorage.setItem("bobodan:scope:documents", JSON.stringify(["doc-1"]));
  });
  const material = { document_id: "doc-1", source: "course/rag.md", kind: "course_document", title: "RAG Lesson", collection: "material", content_role: "content", managed: false };
  const wiki = { document_id: "wiki-1", source: "obsidian/wiki/concepts/RAG.md", kind: "wiki_concept", title: "RAG", collection: "wiki", wiki_type: "concept", content_role: "content", managed: false };
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "Study", default_provider: "deepseek", providers: [{ name: "deepseek", configured: true }], mcp_enabled: false, skills: [] }) }));
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [], wrong_answers: [], weaknesses: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [material] }) }));
  await page.route("**/api/kb/documents?collection=wiki", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [wiki] }) }));
  await page.route("**/api/kb/documents/doc-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: material, sections: [{ chunk_id: "chunk-1", heading: "Retrieval", page_start: 3, text: "RAG uses retrieved evidence." }] }) }));
  await page.route("**/api/kb/documents/wiki-1", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document: wiki, sections: [{ chunk_id: "wiki-chunk", text: "RAG summary" }] }) }));
  const planned = {
    plan_id: "a".repeat(32), status: "planned", action: "generate", instruction: "",
    created_at: "2026-07-13T00:00:00Z",
    scope: { document_ids: ["doc-1"], documents: ["RAG Lesson"] },
    summary: { add: 1, update: 0, merge: 0, conflict: 0, skip: 0 },
    changes: [{
      change_id: "change-1", kind: "add", title: "RAG", page_type: "wiki_concept",
      summary: "Grounded generation.", related: [], source_count: 1, target: "concepts/RAG.md",
      content: "## 原始资料\n\n- [RAG Lesson · Retrieval](/library?collection=material&document=doc-1&chunk=chunk-1)",
    }],
  };
  const focusArtifact = {
    artifact_id: "focus-1", type: "wiki_focus", library_id: "library-1", operation: "generate",
    status: "awaiting_confirmation", summary: "重点整理 RAG 的证据边界。", instruction: "整理核心概念和证据",
    scope: { document_ids: ["doc-1"], documents: ["RAG Lesson"] },
  };
  const planArtifact = { artifact_id: "plan-1", type: "wiki_plan", library_id: "library-1", operation: "generate", status: "planned", plan_id: planned.plan_id, plan: planned };
  const resultArtifact = { artifact_id: "result-1", type: "wiki_result", library_id: "library-1", operation: "apply", status: "applied", plan_id: planned.plan_id, checkpoint_id: "b".repeat(32), written: ["concepts/RAG.md"] };
  let wikiPhase: "focus" | "plan" | "result" = "focus";
  const wikiMessages = () => [
    { role: "user", content: "/wiki plan 整理核心概念和证据" },
    { role: "assistant", content: "重点整理 RAG 的证据边界。", artifacts: [{ ...focusArtifact, status: wikiPhase === "focus" ? "awaiting_confirmation" : "confirmed" }] },
    ...(wikiPhase === "plan" || wikiPhase === "result" ? [{ role: "assistant", content: "已生成 Wiki 计划。", artifacts: [{ ...planArtifact, status: wikiPhase === "result" ? "applied" : "planned", plan: { ...planned, status: wikiPhase === "result" ? "applied" : "planned" } }] }] : []),
    ...(wikiPhase === "result" ? [{ role: "assistant", content: "Wiki 已按确认计划写入。", artifacts: [resultArtifact] }] : []),
  ];
  await page.route("**/api/chat/wiki/focus", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "wiki-session", artifact: focusArtifact }) }));
  await page.route("**/api/chat/sessions/wiki-session", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "wiki-session", name: "RAG Wiki", name_source: "ai", created_at: "2026-07-13T00:00:00Z", last_active: "2026-07-13T00:00:00Z", message_count: wikiMessages().length, messages: wikiMessages() }) }));
  await page.route("**/api/chat/wiki/focus/focus-1/confirm", (route) => { wikiPhase = "plan"; return route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "wiki-session", artifact: planArtifact }) }); });
  await page.route(`**/api/chat/wiki/plans/${planned.plan_id}/apply`, (route) => { wikiPhase = "result"; return route.fulfill({ contentType: "application/json", body: JSON.stringify({ chat_session_id: "wiki-session", artifact: resultArtifact }) }); });

  await page.goto("/library");
  await page.getByRole("button", { name: "整理成 Wiki" }).click();
  await page.getByLabel("整理要求").fill("整理核心概念和证据");
  await page.getByRole("button", { name: "生成计划" }).click();
  await expect(page).toHaveURL(/\/chat/);
  await page.getByRole("textbox", { name: "消息" }).press("Enter");
  await expect(page.getByText("重点整理 RAG 的证据边界。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "按此重点继续" }).click();
  await expect(page.getByRole("region", { name: "Wiki 整理计划" })).toBeVisible();
  await expect(page.getByText("先审查这份整理计划")).toBeVisible();
  await page.getByRole("button", { name: "确认并生成" }).click();
  await expect(page.getByText("Wiki 已写入")).toBeVisible();
  await page.locator(".wiki-plan-change summary").click();
  await page.getByRole("link", { name: /RAG Lesson · Retrieval/ }).click();
  await expect(page).toHaveURL(/collection=material&document=doc-1&chunk=chunk-1/);
  await expect(page.locator('[data-chunk-id="chunk-1"]')).toHaveClass(/highlighted/);
});

test("slash palette exposes commands and local skills", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "测试空间", default_provider: "deepseek", providers: [{ name: "deepseek", configured: true }], mcp_enabled: false, skills: [{ name: "study-loop", description: "推进每日学习闭环。" }, { name: "exam-prep", description: "围绕薄弱点集中复习。" }] }) }));
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
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "测试空间", default_provider: "deepseek", providers: [{ name: "deepseek", configured: true }], mcp_enabled: false }) }));
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

test("Chat and primary study routes render without overlap", async ({ page }, testInfo) => {
  await page.addInitScript(() => localStorage.setItem("bobodan:onboarding:v1", "complete"));
  await page.route("**/api/settings", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ workspace_name: "本地工作区", default_provider: "deepseek", providers: [{ name: "deepseek", configured: true }], mcp_enabled: false, skills: [] }) }));
  const document = { document_id: "visual-doc", source: "course/visual.md", kind: "course_document", title: "视觉测试资料", collection: "material", content_role: "content", managed: false };
  await page.route("**/api/chat/sessions", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/kb/documents?collection=material", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ documents: [document] }) }));
  await page.route("**/api/kb/documents/visual-doc", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ document, sections: [{ chunk_id: "visual-chunk", heading: "资料正文", text: "这是一段用于检查阅读字体、宽度和页面布局的本地资料。" }] }) }));
  await page.route("**/api/quiz/sessions/active", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ sessions: [] }) }));
  await page.route("**/api/learning/review-queue", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ due_concepts: [{ concept: "视觉测试知识点" }], wrong_answers: [], weaknesses: [] }) }));
  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: "今天想学点什么？", level: 2 })).toBeVisible();
  await expect(page.locator(".composer")).toBeVisible();
  await expect(page.locator(".composer-model.connected")).toBeVisible();
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
  await expect(page.getByText("Bobodan 正在处理")).toBeVisible();
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
