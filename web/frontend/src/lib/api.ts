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
  deleteDocument: (id: string) => request<{ document_id: string }>(
    `/api/kb/documents/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  ),
  updateSessionProvider: (id: string, provider: string) => request<{ provider_name: string }>(
    `/api/chat/sessions/${encodeURIComponent(id)}/provider`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider }) },
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
  generateQuestions: (query: string, course?: string, documentIds: string[] = [], webResearchId?: string, webConfirmed = false) => request<{
    status: "ready" | "web_consent_required";
    question_ids?: number[];
    questions?: Question[];
    resolved_query?: string;
    web_research_id?: string;
    query?: string;
    reason?: string;
    suggested_query?: string;
    personalization?: PersonalizationRef[];
  }>(
    "/api/quiz/questions",
    json({ query, course: course || null, count: 5, document_ids: documentIds, web_research_id: webResearchId || null, web_confirmed: webConfirmed }),
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
  reviewQueue: () => request<ReviewQueue>("/api/learning/review-queue"),
  memoryOverview: () => request<MemoryOverview>("/api/memory/overview"),
  memoryKnowledge: (scope = "all", query = "") => request<{ items: PersonalKnowledgeItem[] }>(
    `/api/memory/knowledge?scope=${encodeURIComponent(scope)}&query=${encodeURIComponent(query)}`,
  ),
  createMemoryKnowledge: (body: Pick<PersonalKnowledgeItem, "scope" | "kind" | "title" | "content"> & { pinned?: boolean }) => request<{ item: PersonalKnowledgeItem }>(
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
};

export type ChatStreamEvent =
  | { event: "run_started"; data: { run_id: string; chat_session_id: string } }
  | { event: "message_delta"; data: { content: string } }
  | { event: "status"; data: { phase: string; message: string; tool_name?: string; elapsed?: number } }
  | { event: "citation"; data: { attribution: Attribution } }
  | { event: "chat_artifact"; data: { artifact: ChatArtifact } }
  | { event: "personalization"; data: { references: PersonalizationRef[] } }
  | { event: "practice" | "learning_update"; data: Record<string, unknown> }
  | { event: "run_completed"; data: { chat_session_id: string; termination_reason: string } }
  | { event: "run_failed"; data: { error: { code: string; message: string } } };

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
    references?: ChatReference[];
    strictDocumentScope?: boolean;
  },
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat/runs", {
    ...json({
      message,
      chat_session_id: chatSessionId || null,
      document_ids: preferences.strictDocumentScope ? documentIds : [],
      preferred_document_ids: preferences.strictDocumentScope ? [] : documentIds,
      learning_goal: preferences.learningGoal || "",
      memory_enabled: preferences.memoryEnabled ?? true,
      web_enabled: preferences.webEnabled ?? false,
      web_research_id: preferences.webResearchId || null,
      provider: preferences.provider || null,
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

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const parsed = parseFrame(frame);
      if (parsed) onEvent(parsed);
    }
    if (done) break;
  }
  if (buffer.trim()) {
    const parsed = parseFrame(buffer);
    if (parsed) onEvent(parsed);
  }
}
