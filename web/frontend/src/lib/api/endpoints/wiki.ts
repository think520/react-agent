/** wiki 域的 API 方法（2026-10-17 从 lib/api.ts 逐块搬出，行为不变）。 */
import { json, request } from "../http";
import { } from "../transport";
import type {
  DocumentSummary,
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

} from "../../../types";
import type { } from "../../chatStreamEvents";
import type {


} from "../types";
import type { } from "../transport";

export const wikiApi = {
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
};
