import type {
  Attribution,
  ChatArtifact,
  ChatSessionDetail,
  ChatSessionSummary,
  DocumentSection,
  DocumentSummary,
  DocumentImpact,
  PracticeSession,
  PracticeReadyArtifact,
  Question,
  QuestionBank,
  QuestionSetSummary,
  ReviewQueue,
  SettingsSummary,
  RuntimeStatus,
  SettingsChangeArtifact,
  UserPreferences,
  LibrarySummary,
  LibraryMigrationPreview,
  KnowledgeCandidate,
  LearningEvent,
  LegacyMemoryPreview,
  MemoryConfirmationArtifact,
  MemoryOverview,
  PersonalKnowledgeItem,
  PersonalizationRef,
  ProviderModel,
  ProviderPreset,
  WikiArtifact,
  WikiHealth,
  WikiDocumentCoverage,
  WikiPlan,
  WikiEditablePage,
  WikiGenerationMode,
  WikiRepairPlan,
  WikiRunBudget,
  WikiRunEstimate,
  WikiScopeMode,
  WikiTask,
  WebArtifact,
} from "../types";
import type {  } from "./chatStreamEvents";

import { ApiError, getActiveLibraryId, request, json } from "./api/http";
import { streamQuestionPipeline } from "./api/transport";
export { ApiError, getActiveLibraryId, request, json, setActiveLibraryId } from "./api/http";
export * from "./api/types";
export * from "./api/transport";
import type {  } from "./chatStreamEvents";
import type {
  KnowledgeSyncSummary, KnowledgeTree, ImportBatchResult, ArchivedEntry,
  OrganizationProposalResult, OrganizationBatch,
} from "./api/types";
export const api = {
  libraries: () => request<{ active_library_id: string | null; libraries: LibrarySummary[] }>("/api/libraries"),
  createLibrary: (name: string, parentPath: string) => request<LibrarySummary>(
    "/api/libraries",
    json({ name, parent_path: parentPath }),
  ),
  openLibrary: (path: string) => request<LibrarySummary>("/api/libraries/open", json({ path })),
  previewLibraryMigration: (path: string) => request<LibraryMigrationPreview>(
    "/api/libraries/migrate/preview",
    json({ path }),
  ),
  migrateLibrary: (path: string, name: string) => request<{
    library: LibrarySummary;
    preview: LibraryMigrationPreview;
    sync: Record<string, unknown>;
  }>("/api/libraries/migrate", json({ path, name })),
  activateLibrary: (id: string) => request<LibrarySummary>(
    `/api/libraries/${encodeURIComponent(id)}/activate`,
    { method: "POST" },
  ),
  /** 只读文件夹树（E17 ②）：真实文件夹 + 资料徽章 + 已忽略计数。 */
  /** 新建文件夹 / 删文件夹（只删容器）/ 重命名移动（E17 ③）。 */
  /** 整理建议：只提议，不动文件（E17 ⑤）。 */
  organizationProposals: () => request<OrganizationProposalResult>(
    "/api/kb/organize/proposals",
  ),
  /** 让模型归类（E17 ⑤）：仍然只提议，**一份文件都不动**，执行前还要用户确认。 */
  aiOrganizationProposals: () => request<OrganizationProposalResult>(
    "/api/kb/organize/proposals",
    json({ use_model: true }),
  ),
  applyOrganization: (items: string[], targetFolder: string) => request<{
    ok: boolean;
    moved: { document_id: string; from: string; to: string }[];
    /** 部分失败时：没搬成的那几项（F07 —— 界面必须如实说清楚）。 */
    failed?: { document_id?: string; from: string; to: string; state?: string; error?: string }[];
    batch_id: string;
    partial?: boolean;
  }>("/api/kb/organize/apply", json({ items, target_folder: targetFolder })),
  /** 还有没有一步可以撤销（刷新页面后仍要知道）。 */
  organizationState: () => request<{ ok: boolean; pending_undo: OrganizationBatch | null }>(
    "/api/kb/organize/state",
  ),
  /** 不带清单时撤销服务端台账里的最后一步（刷新 / 重启后依然可撤销）。 */
  undoOrganization: (moves?: { document_id: string; from: string; to: string }[]) => request<{
    ok: boolean;
    restored: string[];
    /** 原位已经有文件、因此**没有**覆盖的那些项（F03）。 */
    skipped?: { from: string; to: string; reason: string }[];
  }>("/api/kb/organize/undo", json(moves ? { moves } : {})),
  createFolder: (path: string) => request<{ ok: boolean; folder: { name: string; path: string } }>(
    "/api/kb/folders",
    json({ path }),
  ),
  deleteFolder: (path: string) => request<{ ok: boolean; moved: string[]; kept_directory: boolean }>(
    "/api/kb/folders/delete",
    json({ path, mode: "ungroup" }),
  ),
  moveDocument: (documentId: string, path: string) => request<{
    ok: boolean;
    migration: { document_id: string; new_source: string; relative_path: string };
  }>(`/api/kb/documents/${encodeURIComponent(documentId)}/move`, json({ path })),
  /** 已归档的资料（归档只是移走，永远可以恢复）。 */
  knowledgeArchive: () => request<{ ok: boolean; entries: ArchivedEntry[] }>("/api/kb/archive"),
  restoreArchived: (entryId: string) => request<{ ok: boolean; restored: ArchivedEntry }>(
    `/api/kb/archive/${encodeURIComponent(entryId)}/restore`,
    { method: "POST" },
  ),
  knowledgeTree: () => request<{ ok: boolean; tree: KnowledgeTree }>("/api/kb/tree"),
  syncLibrary: (id: string) => request<KnowledgeSyncSummary>(
    `/api/libraries/${encodeURIComponent(id)}/sync`,
    { method: "POST" },
  ),
  unregisterLibrary: (id: string) => request<{ unregistered: boolean }>(
    `/api/libraries/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  ),
  settings: () => request<SettingsSummary>("/api/settings"),
  patchPreferences: (revision: number, patch: Record<string, unknown>) => request<{ preferences: UserPreferences }>(
    "/api/settings/preferences",
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ revision, patch }) },
  ),
  providerTest: (provider: string) => request<{ provider: string; model: string; latency_ms: number; response_received: boolean }>(
    `/api/settings/providers/${encodeURIComponent(provider)}/test`,
    { method: "POST" },
  ),
  providerPresets: () => request<{ presets: ProviderPreset[] }>("/api/settings/providers/presets"),
  saveProvider: (body: Record<string, unknown>) => request<{ ok: boolean; name: string }>(
    "/api/settings/providers",
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  ),
  deleteProvider: (name: string) => request<{ ok: boolean; name: string }>(
    `/api/settings/providers/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  ),
  fetchProviderModels: (baseUrl: string, apiKey?: string) => request<{ ok: boolean; models: ProviderModel[] }>(
    "/api/settings/providers/fetch-models",
    json({ base_url: baseUrl, api_key: apiKey || null }),
  ),
  searchProviderTest: (provider: "auto" | "tavily" | "exa") => request<{ provider: string; latency_ms: number; result_count: number }>(
    `/api/settings/search/${encodeURIComponent(provider)}/test`,
    { method: "POST" },
  ),
  runtimeStatus: () => request<RuntimeStatus>("/api/settings/status"),
  llmUsage: (days = 7) => request<{
    days: number; requests: number; errors: number; input_tokens: number; output_tokens: number;
    cache_read_tokens: number; cache_miss_tokens: number; cache_reported: boolean;
    cost_usd: number; cost_reported: boolean; model_distribution: Record<string, number>; provider_distribution: Record<string, number>;
    entries: Array<Record<string, unknown>>;
  }>(`/api/settings/usage?days=${days}`),
  createSettingsProposal: (message: string, chatSessionId?: string) => request<{ chat_session_id: string; artifact: SettingsChangeArtifact }>(
    "/api/settings/proposals",
    json({ message, chat_session_id: chatSessionId || null }),
  ),
  resolveSettingsProposal: (proposalId: string, chatSessionId: string, action: "apply" | "reject") => request<{
    proposal: SettingsChangeArtifact;
    preferences?: UserPreferences | null;
  }>(`/api/settings/proposals/${encodeURIComponent(proposalId)}/${action}`, json({ chat_session_id: chatSessionId })),
  sessions: async () => (await request<{ sessions: ChatSessionSummary[] }>("/api/chat/sessions")).sessions,
  session: (id: string) => request<ChatSessionDetail>(`/api/chat/sessions/${encodeURIComponent(id)}`),
  renameSession: (id: string, name: string) => request<{ name: string }>(
    `/api/chat/sessions/${encodeURIComponent(id)}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) },
  ),
  generateSessionTitle: (id: string) => request<{ name: string; name_source: "ai" | "fallback" | "manual" }>(
    `/api/chat/sessions/${encodeURIComponent(id)}/title`,
    { method: "POST" },
  ),
  deleteSession: (id: string) => request<{ deleted: boolean }>(
    `/api/chat/sessions/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  ),
  documents: async (collection: "all" | "material" | "wiki" = "all") => (
    await request<{ documents: DocumentSummary[] }>(`/api/kb/documents?collection=${collection}`)
  ).documents,
  document: (id: string) => request<{ document: DocumentSummary; sections: DocumentSection[] }>(
    `/api/kb/documents/${encodeURIComponent(id)}`,
  ),
  documentContent: (id: string) => request<{ document: DocumentSummary; content: string; editable: boolean; content_hash: string }>(
    `/api/kb/documents/${encodeURIComponent(id)}/content`,
  ),
  editDocument: (id: string, body: { content: string; expected_hash?: string | null; conflict_action?: "overwrite" | "abandon" | "save_as_new" }) => request<{
    document_id: string; content_hash: string; conflict?: string | null; sync?: Record<string, unknown>;
  }>(
    `/api/kb/documents/${encodeURIComponent(id)}/content`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  ),
  documentVersions: (id: string) => request<{ versions: Array<{ id: string; created_at: string; content_hash: string }> }>(
    `/api/kb/documents/${encodeURIComponent(id)}/versions`,
  ),
  rollbackDocument: (id: string, versionId: string) => request<{ document_id: string; version_id: string; sync?: Record<string, unknown> }>(
    `/api/kb/documents/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/rollback`,
    { method: "POST" },
  ),
  createDocumentProposal: (id: string, body: { instruction: string; provider?: string | null }) => request<{ proposal: import("../types").DocumentProposal }>(
    `/api/kb/documents/${encodeURIComponent(id)}/proposals`,
    json(body),
  ),
  createNewDocumentProposal: (body: { title: string; content: string; reason?: string }) => request<{ proposal: import("../types").DocumentProposal }>(
    "/api/kb/proposals",
    json(body),
  ),
  documentProposal: (id: string) => request<{ proposal: import("../types").DocumentProposal }>(
    `/api/kb/proposals/${encodeURIComponent(id)}`,
  ),
  applyDocumentProposal: (id: string) => request<{ proposal: import("../types").DocumentProposal }>(
    `/api/kb/proposals/${encodeURIComponent(id)}/apply`,
    { method: "POST" },
  ),
  undoDocumentProposal: (id: string) => request<{ proposal: import("../types").DocumentProposal }>(
    `/api/kb/proposals/${encodeURIComponent(id)}/undo`,
    { method: "POST" },
  ),
  deleteDocument: (id: string) => request<{ document_id: string }>(
    `/api/kb/documents/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  ),
  updateSessionProvider: (id: string, provider: string, model?: string) => request<{ provider_name: string; model_name: string | null }>(
    `/api/chat/sessions/${encodeURIComponent(id)}/provider`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider, model: model || null }) },
  ),
  health: () => request<{ ok: boolean }>("/api/health"),
  documentImpact: (id: string) => request<DocumentImpact>(
    `/api/kb/documents/${encodeURIComponent(id)}/impact`,
  ),
  importDocuments: async (files: File[], duplicateStrategy: "keep_existing" | "save_copy" = "keep_existing") => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("duplicate_strategy", duplicateStrategy);
    return request<{
      imported: string[];
      duplicates?: Array<{ filename: string; existing: string; reason: string }>;
      /** 字节已经在库里、这次是**补做索引**的那些（F04）。 */
      pending?: Array<{ filename: string; existing: string; reason: string }>;
      rejected: unknown[];
      /** E8：用户中途取消了这次导入（已收下的保持收下）。 */
      cancelled?: boolean;
      /** 本次上传的逐文件结果（F09：批次计数只认它）。 */
      results?: ImportBatchResult[];
      /** 全库增量同步：单独展示，不当批次计数用。 */
      library_sync: KnowledgeSyncSummary;
    }>(
      "/api/kb/import",
      { method: "POST", body: form },
    );
  },
  /** E8：开始一次**可观察、可取消**的导入（返回 import_id，进度靠轮询）。 */
  startImport: async (files: File[], duplicateStrategy: "keep_existing" | "save_copy" = "keep_existing") => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("duplicate_strategy", duplicateStrategy);
    return request<{ ok: boolean; import_id: string }>(
      "/api/kb/imports",
      { method: "POST", body: form },
    );
  },
  /** E8：读一次导入进度快照（终态时带 result）。 */
  importStatus: (importId: string) => request<{
    import_id: string;
    status: "running" | "completed" | "failed" | "cancelled";
    phase: string;
    files_total: number;
    files_done: number;
    current: string;
    sources_total: number;
    sources_done: number;
    error: string;
    result: {
      imported: string[];
      duplicates?: Array<{ filename: string; existing: string; reason: string }>;
      rejected: unknown[];
      pending?: unknown[];
      cancelled?: boolean;
      results?: ImportBatchResult[];
      library_sync: KnowledgeSyncSummary;
    } | null;
  }>(`/api/kb/imports/${encodeURIComponent(importId)}`),
  /** E8：协作式取消（在文件边界生效，已收下的保持收下）。 */
  cancelImport: (importId: string) => request<{ ok: boolean; cancelled: boolean }>(
    `/api/kb/imports/${encodeURIComponent(importId)}/cancel`,
    { method: "POST" },
  ),  /** W1 E2：新建资料库的默认值 —— 由后端给，前端不再自己拼路径。 */
  libraryDefaults: () => request<{ name: string; parent_path: string; root_path: string }>(
    "/api/libraries/defaults",
  ),
  /** W1 E2：把「父目录 + 名称」翻译成将来真正创建的根目录（与创建走同一套规则）。 */
  libraryRootPreview: (name: string, parent: string) => request<{
    name: string; parent_path: string; root_path: string;
  }>(`/api/libraries/root-preview?name=${encodeURIComponent(name)}&parent=${encodeURIComponent(parent)}`),
  /** W1 E4：跳过这个 ask_user 卡片（关闭交互，由调用方随即恢复暂停的 run）。 */
  skipInteraction: (interactionId: string, chatSessionId: string) =>
    request<{ chat_session_id: string; artifact: ChatArtifact }>(
      "/api/chat/interactions/" + encodeURIComponent(interactionId) + "/skip",
      json({ chat_session_id: chatSessionId, answers: [] }),
    ),
  /** W1 E5：三阶段逐题生成（SSE，边出边收）。 */
  streamQuestionPipeline,
  /** W1 E7：某份资料上的划线（每条都带 resolution：exact / relocated / stale）。 */
  documentAnchors: (documentId: string) => request<{
    anchors: Array<{
      anchor_id: string; document_id: string; chunk_id: string; quote: string;
      char_start: number | null; char_end: number | null; note: string; created_at: string;
      resolution: { status: string; char_start: number | null; char_end: number | null };
    }>;
    count: number;
  }>(`/api/kb/documents/${encodeURIComponent(documentId)}/anchors`),
  createDocumentAnchor: (
    documentId: string,
    body: { chunk_id?: string; quote: string; char_start?: number | null; char_end?: number | null; note?: string },
  ) => request<{ anchor: { anchor_id: string } }>(
    `/api/kb/documents/${encodeURIComponent(documentId)}/anchors`, json(body),
  ),
  deleteDocumentAnchor: (anchorId: string) => request<{ anchor_id: string }>(
    `/api/kb/anchors/${encodeURIComponent(anchorId)}`, { method: "DELETE" },
  ),
  wikiHealth: () => request<WikiHealth>("/api/kb/wiki/maintenance"),
  wikiCoverage: () => request<{ documents: WikiDocumentCoverage[]; counts: Record<string, number> }>("/api/kb/wiki/coverage"),
  maintainWiki: () => request<{ archived_count: number; canonical_count: number; health: WikiHealth; plan_id: string; repair_plan: WikiRepairPlan }>(
    "/api/kb/wiki/maintenance",
    json({ action: "plan" }),
  ),
  reviewWikiSemantics: () => request<{ reviews: unknown[]; health: WikiHealth }>(
    "/api/kb/wiki/maintenance/semantic",
    json({}),
  ),
  wikiTasks: () => request<{ tasks: WikiTask[] }>("/api/kb/wiki/tasks"),
  retryWikiTask: (id: string) => request<{ retry_of: string; result: Record<string, unknown> }>(
    `/api/kb/wiki/tasks/${encodeURIComponent(id)}/retry`,
    json({}),
  ),
  cancelWikiTask: (id: string) => request<{ task: WikiTask }>(
    `/api/kb/wiki/tasks/${encodeURIComponent(id)}/cancel`,
    { method: "POST" },
  ),
  createWikiPlan: (body: {
    action: "generate" | "update";
    document_ids?: string[];
    wiki_document_ids?: string[];
    course?: string | null;
    instruction?: string;
  }) => request<WikiPlan>("/api/kb/wiki/plans", json(body)),
  createWikiRun: (body: {
    action?: "generate" | "update";
    scope_mode: WikiScopeMode;
    document_ids?: string[];
    course?: string | null;
    topic?: string;
    instruction?: string;
    generation_mode?: WikiGenerationMode;
    budget?: WikiRunBudget;
    force_regenerate?: boolean;
  }) => request<WikiPlan>("/api/kb/wiki/runs", json(body)),
  estimateWikiRun: (body: {
    action?: "generate" | "update";
    scope_mode: WikiScopeMode;
    document_ids?: string[];
    course?: string | null;
    topic?: string;
    instruction?: string;
    generation_mode: WikiGenerationMode;
    budget?: WikiRunBudget;
  }) => request<WikiRunEstimate>("/api/kb/wiki/runs/estimate", json(body)),
  wikiRun: (id: string) => request<WikiPlan>(`/api/kb/wiki/runs/${encodeURIComponent(id)}`),
  resumeWikiRun: (id: string, additionalBudget: Partial<WikiRunBudget> = {}) => request<WikiPlan>(
    `/api/kb/wiki/runs/${encodeURIComponent(id)}/resume`, json({ additional_budget: additionalBudget }),
  ),
  cancelWikiRun: (id: string) => request<WikiPlan>(
    `/api/kb/wiki/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" },
  ),
  wikiRunUsage: (id: string) => request<Record<string, unknown>>(`/api/kb/wiki/runs/${encodeURIComponent(id)}/usage`),
  wikiPlan: (id: string) => request<WikiPlan>(`/api/kb/wiki/plans/${encodeURIComponent(id)}`),
  applyWikiPlan: (id: string) => request<WikiPlan & { sync: Record<string, unknown> }>(
    `/api/kb/wiki/plans/${encodeURIComponent(id)}/apply`,
    { method: "POST" },
  ),
  recoverWikiPlan: (id: string, strategy: "keep_existing" | "regenerate") => request<WikiPlan & { sync?: Record<string, unknown> }>(
    `/api/kb/wiki/plans/${encodeURIComponent(id)}/recover`,
    json({ strategy }),
  ),
  restoreWikiCheckpoint: (id: string) => request<{ checkpoint_id: string; restored_at: string; sync: Record<string, unknown> }>(
    `/api/kb/wiki/checkpoints/${encodeURIComponent(id)}/restore`,
    { method: "POST" },
  ),
  wikiRepairPlan: (id: string) => request<WikiRepairPlan>(`/api/kb/wiki/repair-plans/${encodeURIComponent(id)}`),
  draftWikiRepairPlan: (id: string) => request<WikiRepairPlan>(`/api/kb/wiki/repair-plans/${encodeURIComponent(id)}/draft-ai`, json({})),
  applyWikiRepairPlan: (id: string) => request<WikiRepairPlan>(`/api/kb/wiki/repair-plans/${encodeURIComponent(id)}/apply`, { method: "POST" }),
  wikiPage: (id: string) => request<{ page: WikiEditablePage }>(`/api/kb/wiki/pages/${encodeURIComponent(id)}`),
  createWikiPage: (page: { title: string; body: string; tags: string[]; related: string[] }) => request<{ page: DocumentSummary }>("/api/kb/wiki/pages", json(page)),
  updateWikiPage: (id: string, page: { expected_revision: number; title: string; body: string; tags: string[]; related: string[] }) => request<{ page: WikiEditablePage }>(`/api/kb/wiki/pages/${encodeURIComponent(id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(page) }),
  archiveWikiPage: (id: string) => request<{ document_id: string; archived: boolean }>(`/api/kb/wiki/pages/${encodeURIComponent(id)}/archive`, { method: "POST" }),
  restoreWikiPage: (id: string) => request<{ document_id: string; restored: boolean }>(`/api/kb/wiki/pages/${encodeURIComponent(id)}/restore`, { method: "POST" }),
  createWikiFocus: (body: {
    chat_session_id?: string;
    action: "generate" | "update" | "repair" | "migrate";
    scope_mode?: WikiScopeMode;
    document_ids?: string[];
    wiki_document_ids?: string[];
    course?: string | null;
    topic?: string;
    instruction?: string;
  }) => request<{ chat_session_id: string; artifact: WikiArtifact }>("/api/chat/wiki/focus", json(body)),
  reviseWikiFocus: (artifactId: string, chatSessionId: string, revision: string) => request<{ chat_session_id: string; artifact: WikiArtifact }>(
    `/api/chat/wiki/focus/${encodeURIComponent(artifactId)}/revise`,
    json({ chat_session_id: chatSessionId, revision }),
  ),
  confirmWikiFocus: (artifactId: string, chatSessionId: string) => request<{ chat_session_id: string; artifact: WikiArtifact }>(
    `/api/chat/wiki/focus/${encodeURIComponent(artifactId)}/confirm`,
    json({ chat_session_id: chatSessionId }),
  ),
  applyChatWikiPlan: (planId: string, chatSessionId: string) => request<{ chat_session_id: string; artifact: WikiArtifact }>(
    `/api/chat/wiki/plans/${encodeURIComponent(planId)}/apply`,
    json({ chat_session_id: chatSessionId }),
  ),
  recoverChatWikiPlan: (planId: string, chatSessionId: string, strategy: "keep_existing" | "regenerate") => request<{ chat_session_id: string; artifact: WikiArtifact }>(
    `/api/chat/wiki/plans/${encodeURIComponent(planId)}/recover`,
    json({ chat_session_id: chatSessionId, strategy }),
  ),
  cancelChatWikiRun: (runId: string, chatSessionId: string) => request<{ chat_session_id: string; run: WikiPlan }>(
    `/api/chat/wiki/runs/${encodeURIComponent(runId)}/cancel`,
    json({ chat_session_id: chatSessionId }),
  ),
  restoreChatWikiCheckpoint: (checkpointId: string, chatSessionId: string) => request<{ chat_session_id: string; artifact: WikiArtifact }>(
    `/api/chat/wiki/checkpoints/${encodeURIComponent(checkpointId)}/restore`,
    json({ chat_session_id: chatSessionId }),
  ),
  createWebSearch: (query: string, chatSessionId?: string, consentArtifactId?: string, appendUserMessage = false) => request<{ chat_session_id: string; artifact: WebArtifact }>(
    "/api/chat/web/searches",
    json({ query, chat_session_id: chatSessionId || null, consent_artifact_id: consentArtifactId || null, append_user_message: appendUserMessage }),
  ),
  rejectWebConsent: (artifactId: string, chatSessionId: string) => request<{ artifact: WebArtifact }>(
    `/api/chat/web/consents/${encodeURIComponent(artifactId)}/reject`,
    json({ chat_session_id: chatSessionId }),
  ),
  selectWebSources: (searchId: string, chatSessionId: string, candidateIds: string[]) => request<{ chat_session_id: string; artifact: WebArtifact }>(
    `/api/chat/web/searches/${encodeURIComponent(searchId)}/select`,
    json({ chat_session_id: chatSessionId, candidate_ids: candidateIds }),
  ),
  webSource: (snapshotId: string) => request<{ source: Record<string, unknown> }>(
    `/api/chat/web/sources/${encodeURIComponent(snapshotId)}`,
  ),
  activePractice: () => request<{ sessions: Array<{ practice_session_id: number; updated_at: string; question_count: number }> }>(
    "/api/quiz/sessions/active",
  ),
  practice: (id: number) => request<PracticeSession>(`/api/quiz/sessions/${id}`),
  generateQuestions: (
    query: string,
    course?: string,
    documentIds: string[] = [],
    webResearchId?: string,
    webConfirmed = false,
    mode: "generate" | "search" = "generate",
  ) => request<{
    status: "ready" | "web_consent_required";
    question_ids?: number[];
    questions?: Question[];
    resolved_query?: string;
    web_research_id?: string;
    query?: string;
    reason?: string;
    suggested_query?: string;
    personalization?: PersonalizationRef[];
    mode?: "generate" | "search";
  }>(
    "/api/quiz/questions",
    json({
      query,
      course: course || null,
      count: 5,
      document_ids: documentIds,
      web_research_id: webResearchId || null,
      web_confirmed: webConfirmed,
      mode,
    }),
  ),
  startChatPractice: (artifactId: string, chatSessionId: string) => request<{ chat_session_id: string; artifact: PracticeReadyArtifact; practice_session_id: number }>(
    `/api/chat/practice/${encodeURIComponent(artifactId)}/start`,
    json({ chat_session_id: chatSessionId }),
  ),
  startPractice: (
    course?: string,
    questionIds: number[] = [],
    origin: "practice" | "review" | "chat" = "practice",
    personalization: PersonalizationRef[] = [],
  ) => request<{ practice_session_id: number; questions: Question[] }>(
    "/api/quiz/sessions",
    json({ count: 5, course: course || null, question_ids: questionIds, origin, personalization }),
  ),
  submitAnswer: (practiceSessionId: number, questionId: number, answer: string) => request<{
    is_correct: boolean;
    feedback: string;
    correct_answer: string;
    explanation: string;
    attribution?: Attribution;
    mastery_changes: Array<Record<string, unknown>>;
    progress: PracticeSession["progress"];
    session_completed: boolean;
  }>("/api/quiz/answers", json({
    practice_session_id: practiceSessionId,
    question_id: questionId,
    answer,
  })),
  abandonPractice: (id: number) => request(`/api/quiz/sessions/${id}`, { method: "DELETE" }),
  questionBank: (params: {
    state?: string;
    questionId?: number;
    setId?: number;
    qtype?: string;
    difficulty?: string;
    source?: string;
    course?: string;
    concept?: string;
    query?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const search = new URLSearchParams();
    if (params.state && params.state !== "all") search.set("state", params.state);
    if (params.questionId) search.set("question_id", String(params.questionId));
    if (params.setId) search.set("set_id", String(params.setId));
    if (params.qtype) search.set("qtype", params.qtype);
    if (params.difficulty) search.set("difficulty", params.difficulty);
    if (params.source) search.set("source", params.source);
    if (params.course) search.set("course", params.course);
    if (params.concept) search.set("concept", params.concept);
    if (params.query) search.set("q", params.query);
    if (params.limit) search.set("limit", String(params.limit));
    if (params.offset) search.set("offset", String(params.offset));
    const suffix = search.toString();
    return request<QuestionBank>(`/api/quiz/bank${suffix ? `?${suffix}` : ""}`);
  },
  bookmarkQuestion: (questionId: number, bookmarked: boolean) => request<{ question_id: number; bookmarked: boolean }>(
    "/api/quiz/bank/bookmark",
    json({ question_id: questionId, bookmarked }),
  ),
  startBankPractice: (filters: {
    questionIds?: number[];
    state?: string;
    questionType?: string;
    difficulty?: string;
    source?: string;
    concept?: string;
    query?: string;
    limit?: number;
  } = {}) => request<{
    practice_session_id: number;
    questions: Question[];
  }>(
    "/api/quiz/bank/practice",
    json({
      question_ids: filters.questionIds || [],
      state: filters.state || "all",
      question_type: filters.questionType || null,
      difficulty: filters.difficulty || null,
      source: filters.source || null,
      concept: filters.concept || null,
      query: filters.query || null,
      limit: filters.limit || 5,
    }),
  ),
  questionSets: () => request<{ sets: QuestionSetSummary[] }>("/api/quiz/sets"),
  createQuestionSet: (body: {
    name: string;
    questionIds?: number[];
    state?: string;
    questionType?: string;
    difficulty?: string;
    source?: string;
    concept?: string;
    query?: string;
    limit?: number;
  }) => request<{ set_id: number; name: string; question_ids: number[]; question_count: number }>(
    "/api/quiz/sets",
    json({
      name: body.name,
      question_ids: body.questionIds || [],
      state: body.state || "all",
      question_type: body.questionType || null,
      difficulty: body.difficulty || null,
      source: body.source || null,
      concept: body.concept || null,
      query: body.query || null,
      limit: body.limit || 200,
    }),
  ),
  renameQuestionSet: (setId: number, name: string) => request<{ set_id: number; name: string }>(
    `/api/quiz/sets/${setId}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) },
  ),
  deleteQuestionSet: (setId: number) => request<{ set_id: number; deleted: boolean }>(
    `/api/quiz/sets/${setId}`, { method: "DELETE" },
  ),
  addQuestionToSet: (setId: number, questionId: number) => request<{ set_id: number; question_id: number }>(
    `/api/quiz/sets/${setId}/items`, json({ question_id: questionId }),
  ),
  removeQuestionFromSet: (setId: number, questionId: number) => request<{ set_id: number; question_id: number; removed: boolean }>(
    `/api/quiz/sets/${setId}/items/${questionId}`, { method: "DELETE" },
  ),
  startSetPractice: (setId: number, limit = 15) => request<{ practice_session_id: number; questions: Question[] }>(
    `/api/quiz/sets/${setId}/practice?limit=${limit}`, { method: "POST" },
  ),
  exportBankMarkdown: (params: {
    state?: string;
    setId?: number;
    concept?: string;
    qtype?: string;
    difficulty?: string;
    source?: string;
    query?: string;
    includeThirdParty?: boolean;
  } = {}) => {
    const search = new URLSearchParams();
    if (params.state && params.state !== "all") search.set("state", params.state);
    if (params.setId) search.set("set_id", String(params.setId));
    if (params.concept) search.set("concept", params.concept);
    if (params.qtype) search.set("qtype", params.qtype);
    if (params.difficulty) search.set("difficulty", params.difficulty);
    if (params.source) search.set("source", params.source);
    if (params.query) search.set("q", params.query);
    if (params.includeThirdParty) search.set("include_third_party", "true");
    const suffix = search.toString();
    return request<{ markdown: string; count: number; excluded_third_party: number }>(
      `/api/quiz/export/markdown${suffix ? `?${suffix}` : ""}`,
    );
  },
  exportBankBackup: () => request<{ backup: Record<string, unknown> }>("/api/quiz/export/backup"),
  restoreBankBackup: (backup: Record<string, unknown>) => request<{ restored: Record<string, number> }>(
    "/api/quiz/export/restore", json({ backup }),
  ),
  reviewQueue: () => request<ReviewQueue>("/api/learning/review-queue"),
  answerInteraction: (interactionId: string, chatSessionId: string, answers: Array<{ id: string; answer: string }>) =>
    request<{ chat_session_id: string; artifact: ChatArtifact }>(
      "/api/chat/interactions/" + encodeURIComponent(interactionId) + "/answer",
      json({ chat_session_id: chatSessionId, answers }),
    ),
  conceptMastery: (concept: string) => request<{
    concept: string;
    status?: string;
    score?: number;
    review_count?: number;
    next_review?: string | null;
  }>(`/api/learning/progress?concept=${encodeURIComponent(concept)}`),
  generateWrongAnswerVariant: (attemptId: number) => request<{
    question_id: number;
    question: Question;
    mode?: string;
    /** W1 E3：更精确的归因（evidence_used / evidence_missing / variant_failed / no_provider / generation_failed）。 */
    reason?: string;
  }>(
    "/api/quiz/wrong/variant",
    json({ attempt_id: attemptId }),
  ),
  memoryOverview: () => request<MemoryOverview>("/api/memory/overview"),
  memoryKnowledge: (scope = "all", query = "") => request<{ items: PersonalKnowledgeItem[] }>(
    `/api/memory/knowledge?scope=${encodeURIComponent(scope)}&query=${encodeURIComponent(query)}`,
  ),
  knowledgeByDocument: (documentId: string) => request<{ items: PersonalKnowledgeItem[] }>(
    `/api/memory/knowledge/by-document/${encodeURIComponent(documentId)}`,
  ),
  createMemoryKnowledge: (body: Pick<PersonalKnowledgeItem, "scope" | "kind" | "title" | "content"> & { pinned?: boolean; references?: PersonalKnowledgeItem["references"] }) => request<{ item: PersonalKnowledgeItem }>(
    "/api/memory/knowledge", json(body),
  ),
  updateMemoryKnowledge: (id: string, revision: number, patch: Record<string, unknown>) => request<{ item: PersonalKnowledgeItem }>(
    `/api/memory/knowledge/${encodeURIComponent(id)}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ revision, patch }) },
  ),
  deleteMemoryKnowledge: (id: string) => request<{ deleted: boolean }>(
    `/api/memory/knowledge/${encodeURIComponent(id)}`, { method: "DELETE" },
  ),
  memoryCandidates: () => request<{ candidates: KnowledgeCandidate[] }>("/api/memory/candidates"),
  confirmMemoryCandidate: (id: string, edits: Record<string, unknown>) => request<{ item: PersonalKnowledgeItem; candidate: KnowledgeCandidate }>(
    `/api/memory/candidates/${encodeURIComponent(id)}/confirm`, json({ edits }),
  ),
  rejectMemoryCandidate: (id: string) => request<{ candidate: KnowledgeCandidate }>(
    `/api/memory/candidates/${encodeURIComponent(id)}/reject`, json({}),
  ),
  memoryEvents: () => request<{ events: LearningEvent[] }>("/api/memory/events?limit=200"),
  updateReadingProgress: (documentId: string, progress: number, opened = false) => request<{ progress: { document_id: string; progress: number } }>(
    `/api/memory/reading-progress/${encodeURIComponent(documentId)}`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ progress, opened }) },
  ),
  legacyMemoryPreview: () => request<LegacyMemoryPreview>("/api/memory/legacy/preview"),
  importLegacyMemory: (selections: Array<{ name: string; scope: "global" | "library"; kind: string }>) => request<{ created: KnowledgeCandidate[]; skipped: string[] }>(
    "/api/memory/legacy/import", json({ selections }),
  ),
  exportMemory: async (scope: "global" | "library" | "all" = "all") => {
    const headers = new Headers();
    if (getActiveLibraryId()) headers.set("X-Bobodan-Library-ID", getActiveLibraryId());
    const response = await fetch(`/api/memory/export?scope=${scope}`, { headers });
    if (!response.ok) throw new ApiError(`导出失败 (${response.status})`, "memory_export_failed", response.status);
    return response.text();
  },
  resolveMemoryProposal: (artifactId: string, chatSessionId: string, action: "confirm" | "reject", warningAcknowledged = false) => request<{ artifact: MemoryConfirmationArtifact }>(
    `/api/chat/memory/proposals/${encodeURIComponent(artifactId)}/${action}`,
    json({ chat_session_id: chatSessionId, warning_acknowledged: warningAcknowledged }),
  ),

  // Knowledge Map — P5E.6
  graphState: (opts: { topic_id?: string; include_candidates?: boolean; view_id?: string } = {}) => {
    const params = new URLSearchParams();
    if (opts.topic_id) params.set("topic_id", opts.topic_id);
    if (opts.include_candidates) params.set("include_candidates", "true");
    if (opts.view_id) params.set("view_id", opts.view_id);
    const qs = params.toString();
    return request<import("../types").GraphState>(`/api/graph/state${qs ? `?${qs}` : ""}`);
  },
  legacyGraphPreview: () => request<import("../types").LegacyGraphPreview>("/api/graph/legacy/preview"),
  importLegacyGraph: (conceptIds: string[], memoryIds: string[]) => request<{
    concept_candidates: import("../types").ConceptCandidate[];
    memory_candidates: import("../types").KnowledgeCandidate[];
    archived: boolean;
  }>("/api/graph/legacy/import", json({ concept_ids: conceptIds, memory_ids: memoryIds, archive: true })),
  graphSubgraph: (conceptId: string, viewId?: string) =>
    request<import("../types").GraphSubgraph>(
      `/api/graph/subgraph/${encodeURIComponent(conceptId)}${viewId ? `?view_id=${encodeURIComponent(viewId)}` : ""}`,
    ),
  graphConcept: (conceptId: string) =>
    request<import("../types").ConceptDetail>(`/api/graph/concepts/${encodeURIComponent(conceptId)}`),
  graphUpsertConcept: (body: Record<string, unknown>) =>
    request<{ concept: import("../types").ConceptNode }>("/api/graph/concepts", json(body)),
  graphPatchConcept: (conceptId: string, body: Record<string, unknown>) =>
    request<{ concept: import("../types").ConceptNode }>(
      `/api/graph/concepts/${encodeURIComponent(conceptId)}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    ),
  graphDeleteConcept: (conceptId: string) =>
    request<{ ok: boolean }>(`/api/graph/concepts/${encodeURIComponent(conceptId)}`, { method: "DELETE" }),
  graphAddRelationship: (body: Record<string, unknown>) =>
    request<{ relationship: import("../types").RelationshipEdge }>("/api/graph/relationships", json(body)),
  graphDeleteRelationship: (relId: string) =>
    request<{ ok: boolean }>(`/api/graph/relationships/${encodeURIComponent(relId)}`, { method: "DELETE" }),
  // Graph edit (TASKS_LIBRARY_REWORK task 4): validated user edits at /api/kb.
  updateConcept: (conceptId: string, body: { name?: string; definition?: string; aliases?: string[]; note?: string }) =>
    request<{ concept: import("../types").ConceptNode }>(
      `/api/kb/concepts/${encodeURIComponent(conceptId)}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    ),
  createRelationship: (body: { from_id: string; to_id: string; rel_type: string; note?: string }) =>
    request<{ relationship: import("../types").RelationshipEdge }>("/api/kb/relationships", json(body)),
  deleteRelationship: (relId: string) =>
    request<{ ok: boolean }>(`/api/kb/relationships/${encodeURIComponent(relId)}`, { method: "DELETE" }),
  graphCandidates: (status = "pending", documentId?: string) =>
    request<{ candidates: import("../types").ConceptCandidate[]; count: number }>(
      `/api/graph/candidates?status=${encodeURIComponent(status)}${documentId ? `&document_id=${encodeURIComponent(documentId)}` : ""}`,
    ),
  graphCandidateAction: (
    candidateId: string,
    action: "confirm" | "reject" | "label",
    suppressDays = 14,
    relationEdits: Array<{ candidate_id: string; index: number; enabled: boolean; rel_type: string; direction: "outgoing" | "incoming" }> = [],
  ) =>
    request<{ concept?: import("../types").ConceptNode }>(
      `/api/graph/candidates/${encodeURIComponent(candidateId)}/action`,
      json({ action, suppress_days: suppressDays, relation_edits: relationEdits }),
    ),
  graphConfirmCandidates: (
    candidateIds: string[],
    relationEdits: Array<{ candidate_id: string; index: number; enabled: boolean; rel_type: string; direction: "outgoing" | "incoming" }>,
  ) => request<{ concepts: import("../types").ConceptNode[]; relationships: import("../types").RelationshipEdge[] }>(
    "/api/graph/candidates/confirm",
    json({ candidate_ids: candidateIds, relation_edits: relationEdits }),
  ),
  graphExtract: (body: { document_id: string; document_title: string; content: string; sections?: import("../types").DocumentSection[]; document_path?: string; provider?: string }) =>
    request<{ stored: number; tags: string[]; pending_total: number }>("/api/graph/extract", json(body)),
  graphStartExtraction: (body: { document_id: string; document_title: string; content: string; sections?: import("../types").DocumentSection[]; document_path?: string; content_version?: string; provider?: string; force?: boolean }) =>
    request<{ run: import("../types").GraphExtractionRun; started: boolean }>("/api/graph/extractions", json(body)),
  graphExtractionStatuses: () =>
    request<{ documents: Record<string, import("../types").DocumentExtractionStatus> }>("/api/graph/extractions"),
  graphExtraction: (runId: string) =>
    request<{ run: import("../types").GraphExtractionRun }>(
      `/api/graph/extractions/${encodeURIComponent(runId)}`,
    ),
  graphRetryFailedSections: (
    runId: string,
    body: { document_id: string; document_title: string; content: string; sections: import("../types").DocumentSection[]; content_version?: string; provider?: string },
  ) => request<{ run: import("../types").GraphExtractionRun; started: boolean; retried_sections: number }>(
    `/api/graph/extractions/${encodeURIComponent(runId)}/retry`,
    json(body),
  ),
  /** ④ 原文检索：命中带 chunk_id，可直接深链到阅读器定位那一段。 */
  searchKnowledge: (query: string, collection = "material") =>
    request<{ ok: boolean; results: Array<{ chunk_id: string; document_id: string; collection?: string; title?: string; source?: string; text?: string; score?: number }> }>(
      "/api/kb/search",
      json({ query, top_k: 10, collection }),
    ),
  graphSavePositions: (positions: Array<{ concept_id: string; x: number; y: number }>, viewId = "default") =>
    request<{ saved: number }>("/api/graph/positions", json({ positions, view_id: viewId })),
  // P0-1: a run outlives its fetch now, so stopping one is a request to the
  // server rather than a side effect of closing the connection.
  cancelRun: (streamId: string) =>
    request<{ ok: boolean; cancelled: boolean }>(
      "/api/chat/streams/" + encodeURIComponent(streamId) + "/cancel",
      { method: "POST" },
    ),
};
