import type {
  Attribution,
  ChatArtifact,
  ChatSessionDetail,
  ChatSessionSummary,
  ChatReference,
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

interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: unknown };
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code = "request_failed",
    public readonly status = 0,
    public readonly details?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (activeLibraryId && path.startsWith("/api/") && !path.startsWith("/api/libraries")) {
    headers.set("X-Bobodan-Library-ID", activeLibraryId);
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let body: ErrorEnvelope = {};
    try {
      body = (await response.json()) as ErrorEnvelope;
    } catch {
      // The fallback below remains user-readable when a proxy or server returns HTML.
    }
    throw new ApiError(
      body.error?.message || `请求失败 (${response.status})`,
      body.error?.code,
      response.status,
      body.error?.details,
    );
  }
  return response.json() as Promise<T>;
}

let activeLibraryId = localStorage.getItem("bobodan:library:active") || "";

export function setActiveLibraryId(libraryId: string | null) {
  activeLibraryId = libraryId || "";
  if (activeLibraryId) localStorage.setItem("bobodan:library:active", activeLibraryId);
  else localStorage.removeItem("bobodan:library:active");
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

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
  syncLibrary: (id: string) => request<Record<string, unknown>>(
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
  importDocuments: async (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request<{ imported: string[]; rejected: unknown[]; sync: Record<string, unknown> }>(
      "/api/kb/import",
      { method: "POST", body: form },
    );
  },
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
  generateWrongAnswerVariant: (attemptId: number) => request<{ question_id: number; question: Question; mode?: string }>(
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
    if (activeLibraryId) headers.set("X-Bobodan-Library-ID", activeLibraryId);
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

interface StreamFrameMeta {
  stream_id?: string;
  seq?: number;
}

export type ChatStreamEvent =
  | { event: "run_started"; data: { run_id: string; chat_session_id: string } & StreamFrameMeta }
  | { event: "message_delta"; data: { content: string } & StreamFrameMeta }
  | { event: "status"; data: { phase: string; message: string; tool_name?: string; elapsed?: number } & StreamFrameMeta }
  | { event: "citation"; data: { attribution: Attribution } & StreamFrameMeta }
  | { event: "chat_artifact"; data: { artifact: ChatArtifact } & StreamFrameMeta }
  | { event: "personalization"; data: { references: PersonalizationRef[] } & StreamFrameMeta }
  | { event: "practice" | "learning_update"; data: Record<string, unknown> & StreamFrameMeta }
  | { event: "run_completed"; data: { chat_session_id: string; termination_reason: string } & StreamFrameMeta }
  | { event: "run_failed"; data: { error: { code: string; message: string } } & StreamFrameMeta };

/** Backoff for resuming a run after its reader broke (P0-1). */
export const RESUME_DELAYS_MS = [300, 900, 2000];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Asset URL for an image referenced by a document (relative markdown paths).
 *
 * <img> cannot carry the library header, so the id travels in the query string -
 * the backend still requires it to resolve to a registered library, and the
 * resolved path to stay inside the workspace. Absolute/data/blob sources are
 * left alone: they are not ours to rewrite.
 */
/** The original file's text, for the in-page original view (md/txt only). */
export async function fetchDocumentRawText(documentId: string): Promise<string> {
  const response = await fetch(documentRawUrl(documentId), {
    headers: activeLibraryId ? { "X-Bobodan-Library-ID": activeLibraryId } : undefined,
  });
  if (!response.ok) {
    throw new ApiError(
      "无法读取原文 (" + response.status + ")",
      "document_raw_unavailable",
      response.status,
    );
  }
  return response.text();
}

/**
 * Split leading YAML frontmatter so the reader can *fold* it instead of either
 * dumping it at the top of every article or quietly hiding part of the file.
 */
export function splitFrontmatter(text: string): { meta: string; body: string } {
  const match = /^\uFEFF?---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text || "");
  if (!match) return { meta: "", body: text || "" };
  return { meta: match[1].trim(), body: (text || "").slice(match[0].length) };
}


/**
 * Raw URL suitable for an <iframe>/<img>: those requests cannot carry the
 * library header, so the id travels in the query string (the backend accepts it
 * for media routes only, and still requires a registered library).
 */
export function documentRawEmbedUrl(documentId: string): string {
  const base = documentRawUrl(documentId);
  return activeLibraryId ? base + "?library=" + encodeURIComponent(activeLibraryId) : base;
}


export function documentAssetUrl(documentId: string, source: string): string {
  if (!source || /^(https?:|data:|blob:|\/)/i.test(source)) return source;
  const base =
    "/api/kb/documents/" + encodeURIComponent(documentId) + "/asset?path=" + encodeURIComponent(source);
  return activeLibraryId ? base + "&library=" + encodeURIComponent(activeLibraryId) : base;
}


export function documentRawUrl(documentId: string): string {
  return "/api/kb/documents/" + encodeURIComponent(documentId) + "/raw";
}

/**
 * Open the original file in a new tab (原文查看).
 *
 * Parsing loses images and flattens tables, so the reader has to be able to see
 * the file itself. A plain <a href> cannot carry the library header, so the
 * bytes are fetched first and handed to the browser as a blob - PDFs still land
 * in the built-in viewer, and what arrives is the untouched original.
 */
export async function openDocumentRaw(documentId: string): Promise<void> {
  // Open the tab *synchronously*: once we await, the user gesture is gone and
  // popup blockers win. "noopener" is set by hand because passing it to
  // window.open makes the returned handle unusable.
  const target = window.open("", "_blank");
  if (!target) {
    throw new ApiError("浏览器拦截了新标签页", "popup_blocked", 0);
  }
  target.opener = null;
  try {
    const response = await fetch(documentRawUrl(documentId), {
      headers: activeLibraryId ? { "X-Bobodan-Library-ID": activeLibraryId } : undefined,
    });
    if (!response.ok) {
      throw new ApiError(
        "无法打开原文 (" + response.status + ")",
        "document_raw_unavailable",
        response.status,
      );
    }
    const url = URL.createObjectURL(await response.blob());
    target.location.href = url;
    // The viewer needs the URL while it is open; revoke lazily.
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (error) {
    target.close();
    throw error;
  }
}


export function parseFrame(frame: string): ChatStreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) } as ChatStreamEvent;
  } catch {
    // A malformed frame must not break the rest of the stream.
    console.warn("[bobodan] 跳过无法解析的 SSE 帧", { event, frame });
    return null;
  }
}

export async function streamChat(
  message: string,
  chatSessionId: string | undefined,
  documentIds: string[],
  preferences: {
    learningGoal?: string;
    memoryEnabled?: boolean;
    webEnabled?: boolean;
    webResearchId?: string;
    provider?: string;
    model?: string;
    references?: ChatReference[];
    strictDocumentScope?: boolean;
    /** E4: continue a paused ask_user turn instead of sending a new message. */
    resumeInteractionId?: string;
    /** P0-1: called with the stream id as soon as a frame names it. */
    onStreamId?: (streamId: string) => void;
  },
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat/runs", {
    ...json({
      message,
      resume_interaction_id: preferences.resumeInteractionId || null,
      chat_session_id: chatSessionId || null,
      document_ids: preferences.strictDocumentScope ? documentIds : [],
      preferred_document_ids: preferences.strictDocumentScope ? [] : documentIds,
      learning_goal: preferences.learningGoal || "",
      memory_enabled: preferences.memoryEnabled ?? true,
      web_enabled: preferences.webEnabled ?? false,
      web_research_id: preferences.webResearchId || null,
      provider: preferences.provider || null,
      model: preferences.model || null,
      references: preferences.references || [],
      save: true,
    }),
    headers: activeLibraryId ? {
      "Content-Type": "application/json",
      "X-Bobodan-Library-ID": activeLibraryId,
    } : { "Content-Type": "application/json" },
    signal,
  });
  if (!response.ok || !response.body) {
    let error: ErrorEnvelope = {};
    try {
      error = (await response.json()) as ErrorEnvelope;
    } catch {
      // Keep the fallback when a proxy returns a non-JSON response.
    }
    throw new ApiError(
      error.error?.message || `无法开始对话 (${response.status})`,
      error.error?.code || "chat_unavailable",
      response.status,
      error.error?.details,
    );
  }

  // De-duplicate replayed frames on reconnect (AG-0.3): each frame carries a
  // monotonic seq; an already-consumed seq must never render twice. P0-1 made
  // that dedup load-bearing: a dropped reader now resumes instead of failing.
  const consumedSeqs = new Set<number>();
  let lastSeq = 0;
  let streamId = "";
  let terminal = false;
  const dispatch = (parsed: ChatStreamEvent) => {
    const seq = parsed.data.seq;
    if (typeof seq === "number" && consumedSeqs.has(seq)) return;
    if (typeof seq === "number") {
      consumedSeqs.add(seq);
      if (seq > lastSeq) lastSeq = seq;
    }
    if (!streamId && parsed.data.stream_id) {
      streamId = parsed.data.stream_id;
      // The stop button cancels the *run*, which no longer lives in this
      // response, so it needs the id as soon as one frame names it.
      preferences.onStreamId?.(streamId);
    }
    if (parsed.event === "run_completed" || parsed.event === "run_failed") terminal = true;
    onEvent(parsed);
  };
  const pump = async (body: ReadableStream<Uint8Array>): Promise<number> => {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let frames = 0;
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const parts = buffer.split(/\r?\n\r?\n/);
      buffer = parts.pop() || "";
      for (const frame of parts) {
        const parsed = parseFrame(frame);
        if (parsed) {
          frames += 1;
          dispatch(parsed);
        }
      }
      if (done) break;
    }
    if (buffer.trim()) {
      const parsed = parseFrame(buffer);
      if (parsed) {
        frames += 1;
        dispatch(parsed);
      }
    }
    return frames;
  };
  const openResume = async (
    id: string,
    after: number,
  ): Promise<ReadableStream<Uint8Array> | null> => {
    try {
      const resumed = await fetch(
        "/api/chat/streams/" + encodeURIComponent(id) + "/replay?after_seq=" + after,
        { headers: { "Last-Event-ID": String(after) }, signal },
      );
      return resumed.ok && resumed.body ? resumed.body : null;
    } catch (error) {
      if (signal?.aborted) throw error;
      return null;
    }
  };

  let networkError: unknown = null;
  try {
    await pump(response.body);
  } catch (error) {
    // A broken reader is recoverable now: the run keeps going on the server.
    if (signal?.aborted) throw error;
    networkError = error;
  }

  // Only a *broken* reader resumes: a clean end without a terminal event is
  // the server saying the run is over, and retrying it would just add delay.
  if (networkError != null && !terminal && streamId) {
    for (const delay of RESUME_DELAYS_MS) {
      if (terminal) break;
      await sleep(delay);
      const body = await openResume(streamId, lastSeq);
      if (!body) continue;
      try {
        // Zero frames after our cursor means the log has nothing left for us,
        // which is exactly how a run that already finished looks.
        if ((await pump(body)) === 0) break;
      } catch (error) {
        // This attempt broke too: keep the remaining delays instead of giving
        // up on the run after the first unlucky reconnect.
        if (signal?.aborted) throw error;
        networkError = error;
        continue;
      }
    }
  }
  // Nothing resumed and nothing terminal: report the original failure instead
  // of returning a silently truncated answer.
  if (!terminal && networkError) throw networkError;
}
