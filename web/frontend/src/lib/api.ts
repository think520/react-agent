import type {
  Attribution,
  ChatSessionDetail,
  ChatSessionSummary,
  DocumentSection,
  DocumentSummary,
  PracticeSession,
  Question,
  ReviewQueue,
  SettingsSummary,
  LibrarySummary,
  LibraryMigrationPreview,
  WikiArtifact,
  WikiHealth,
  WikiPlan,
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
  importDocuments: async (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request<{ imported: string[]; rejected: unknown[]; sync: Record<string, unknown> }>(
      "/api/kb/import",
      { method: "POST", body: form },
    );
  },
  wikiHealth: () => request<WikiHealth>("/api/kb/wiki/maintenance"),
  maintainWiki: () => request<{ archived_count: number; canonical_count: number; health: WikiHealth }>(
    "/api/kb/wiki/maintenance",
    json({ action: "organize" }),
  ),
  createWikiPlan: (body: {
    action: "generate" | "update";
    document_ids?: string[];
    wiki_document_ids?: string[];
    course?: string | null;
    instruction?: string;
  }) => request<WikiPlan>("/api/kb/wiki/plans", json(body)),
  wikiPlan: (id: string) => request<WikiPlan>(`/api/kb/wiki/plans/${encodeURIComponent(id)}`),
  applyWikiPlan: (id: string) => request<WikiPlan & { sync: Record<string, unknown> }>(
    `/api/kb/wiki/plans/${encodeURIComponent(id)}/apply`,
    { method: "POST" },
  ),
  restoreWikiCheckpoint: (id: string) => request<{ checkpoint_id: string; restored_at: string; sync: Record<string, unknown> }>(
    `/api/kb/wiki/checkpoints/${encodeURIComponent(id)}/restore`,
    { method: "POST" },
  ),
  createWikiFocus: (body: {
    chat_session_id?: string;
    action: "generate" | "update" | "repair" | "migrate";
    document_ids?: string[];
    wiki_document_ids?: string[];
    course?: string | null;
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
  restoreChatWikiCheckpoint: (checkpointId: string, chatSessionId: string) => request<{ chat_session_id: string; artifact: WikiArtifact }>(
    `/api/chat/wiki/checkpoints/${encodeURIComponent(checkpointId)}/restore`,
    json({ chat_session_id: chatSessionId }),
  ),
  activePractice: () => request<{ sessions: Array<{ practice_session_id: number; updated_at: string; question_count: number }> }>(
    "/api/quiz/sessions/active",
  ),
  practice: (id: number) => request<PracticeSession>(`/api/quiz/sessions/${id}`),
  generateQuestions: (query: string, course?: string, documentIds: string[] = []) => request<{ question_ids: number[]; questions: Question[] }>(
    "/api/quiz/questions",
    json({ query, course: course || null, count: 5, document_ids: documentIds }),
  ),
  startPractice: (course?: string, questionIds: number[] = []) => request<{ practice_session_id: number; questions: Question[] }>(
    "/api/quiz/sessions",
    json({ count: 5, course: course || null, question_ids: questionIds }),
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
};

export type ChatStreamEvent =
  | { event: "run_started"; data: { run_id: string; chat_session_id: string } }
  | { event: "message_delta"; data: { content: string } }
  | { event: "status"; data: { phase: string; message: string; tool_name?: string; elapsed?: number } }
  | { event: "citation"; data: { attribution: Attribution } }
  | { event: "practice" | "learning_update"; data: Record<string, unknown> }
  | { event: "run_completed"; data: { chat_session_id: string; termination_reason: string } }
  | { event: "run_failed"; data: { error: { code: string; message: string } } };

function parseFrame(frame: string): ChatStreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  return { event, data: JSON.parse(dataLines.join("\n")) } as ChatStreamEvent;
}

export async function streamChat(
  message: string,
  chatSessionId: string | undefined,
  documentIds: string[],
  preferences: { learningGoal?: string; memoryEnabled?: boolean; webEnabled?: boolean },
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat/runs", {
    ...json({
      message,
      chat_session_id: chatSessionId || null,
      document_ids: documentIds,
      learning_goal: preferences.learningGoal || "",
      memory_enabled: preferences.memoryEnabled ?? true,
      web_enabled: preferences.webEnabled ?? false,
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
