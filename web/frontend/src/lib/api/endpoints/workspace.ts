/** workspace 域的 API 方法（2026-10-17 从 lib/api.ts 逐块搬出，行为不变）。 */
import { ApiError, getActiveLibraryId, json, request } from "../http";
import { } from "../transport";
import type {
  SettingsSummary,
  RuntimeStatus,
  SettingsChangeArtifact,
  UserPreferences,
  KnowledgeCandidate,
  LearningEvent,
  LegacyMemoryPreview,
  MemoryConfirmationArtifact,
  MemoryOverview,
  PersonalKnowledgeItem,
  ProviderModel,
  ProviderPreset,












} from "../../../types";
import type { } from "../../chatStreamEvents";
import type {


} from "../types";
import type { } from "../transport";

export const workspaceApi = {
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
    return request<import("../../../types").GraphState>(`/api/graph/state${qs ? `?${qs}` : ""}`);
  },
  legacyGraphPreview: () => request<import("../../../types").LegacyGraphPreview>("/api/graph/legacy/preview"),
  importLegacyGraph: (conceptIds: string[], memoryIds: string[]) => request<{
    concept_candidates: import("../../../types").ConceptCandidate[];
    memory_candidates: import("../../../types").KnowledgeCandidate[];
    archived: boolean;
  }>("/api/graph/legacy/import", json({ concept_ids: conceptIds, memory_ids: memoryIds, archive: true })),
  graphSubgraph: (conceptId: string, viewId?: string) =>
    request<import("../../../types").GraphSubgraph>(
      `/api/graph/subgraph/${encodeURIComponent(conceptId)}${viewId ? `?view_id=${encodeURIComponent(viewId)}` : ""}`,
    ),
  graphConcept: (conceptId: string) =>
    request<import("../../../types").ConceptDetail>(`/api/graph/concepts/${encodeURIComponent(conceptId)}`),
  graphUpsertConcept: (body: Record<string, unknown>) =>
    request<{ concept: import("../../../types").ConceptNode }>("/api/graph/concepts", json(body)),
  graphPatchConcept: (conceptId: string, body: Record<string, unknown>) =>
    request<{ concept: import("../../../types").ConceptNode }>(
      `/api/graph/concepts/${encodeURIComponent(conceptId)}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    ),
  graphDeleteConcept: (conceptId: string) =>
    request<{ ok: boolean }>(`/api/graph/concepts/${encodeURIComponent(conceptId)}`, { method: "DELETE" }),
  graphAddRelationship: (body: Record<string, unknown>) =>
    request<{ relationship: import("../../../types").RelationshipEdge }>("/api/graph/relationships", json(body)),
  graphDeleteRelationship: (relId: string) =>
    request<{ ok: boolean }>(`/api/graph/relationships/${encodeURIComponent(relId)}`, { method: "DELETE" }),
  // Graph edit (TASKS_LIBRARY_REWORK task 4): validated user edits at /api/kb.
  updateConcept: (conceptId: string, body: { name?: string; definition?: string; aliases?: string[]; note?: string }) =>
    request<{ concept: import("../../../types").ConceptNode }>(
      `/api/kb/concepts/${encodeURIComponent(conceptId)}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    ),
  createRelationship: (body: { from_id: string; to_id: string; rel_type: string; note?: string }) =>
    request<{ relationship: import("../../../types").RelationshipEdge }>("/api/kb/relationships", json(body)),
  deleteRelationship: (relId: string) =>
    request<{ ok: boolean }>(`/api/kb/relationships/${encodeURIComponent(relId)}`, { method: "DELETE" }),
  graphCandidates: (status = "pending", documentId?: string) =>
    request<{ candidates: import("../../../types").ConceptCandidate[]; count: number }>(
      `/api/graph/candidates?status=${encodeURIComponent(status)}${documentId ? `&document_id=${encodeURIComponent(documentId)}` : ""}`,
    ),
  graphCandidateAction: (
    candidateId: string,
    action: "confirm" | "reject" | "label",
    suppressDays = 14,
    relationEdits: Array<{ candidate_id: string; index: number; enabled: boolean; rel_type: string; direction: "outgoing" | "incoming" }> = [],
  ) =>
    request<{ concept?: import("../../../types").ConceptNode }>(
      `/api/graph/candidates/${encodeURIComponent(candidateId)}/action`,
      json({ action, suppress_days: suppressDays, relation_edits: relationEdits }),
    ),
  graphConfirmCandidates: (
    candidateIds: string[],
    relationEdits: Array<{ candidate_id: string; index: number; enabled: boolean; rel_type: string; direction: "outgoing" | "incoming" }>,
  ) => request<{ concepts: import("../../../types").ConceptNode[]; relationships: import("../../../types").RelationshipEdge[] }>(
    "/api/graph/candidates/confirm",
    json({ candidate_ids: candidateIds, relation_edits: relationEdits }),
  ),
  graphExtract: (body: { document_id: string; document_title: string; content: string; sections?: import("../../../types").DocumentSection[]; document_path?: string; provider?: string }) =>
    request<{ stored: number; tags: string[]; pending_total: number }>("/api/graph/extract", json(body)),
  graphStartExtraction: (body: { document_id: string; document_title: string; content: string; sections?: import("../../../types").DocumentSection[]; document_path?: string; content_version?: string; provider?: string; force?: boolean }) =>
    request<{ run: import("../../../types").GraphExtractionRun; started: boolean }>("/api/graph/extractions", json(body)),
  graphExtractionStatuses: () =>
    request<{ documents: Record<string, import("../../../types").DocumentExtractionStatus> }>("/api/graph/extractions"),
  graphExtraction: (runId: string) =>
    request<{ run: import("../../../types").GraphExtractionRun }>(
      `/api/graph/extractions/${encodeURIComponent(runId)}`,
    ),
  graphRetryFailedSections: (
    runId: string,
    body: { document_id: string; document_title: string; content: string; sections: import("../../../types").DocumentSection[]; content_version?: string; provider?: string },
  ) => request<{ run: import("../../../types").GraphExtractionRun; started: boolean; retried_sections: number }>(
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
};
