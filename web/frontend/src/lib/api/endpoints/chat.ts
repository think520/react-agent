/** chat 域的 API 方法（2026-10-17 从 lib/api.ts 逐块搬出，行为不变）。 */
import { json, request } from "../http";
import { streamQuestionPipeline } from "../transport";
import type {
  ChatArtifact,
  ChatSessionDetail,
  ChatSessionSummary,
  WebArtifact,
} from "../../../types";
import type { } from "../../chatStreamEvents";
import type {


} from "../types";
import type { } from "../transport";

export const chatApi = {
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
  health: () => request<{ ok: boolean }>("/api/health"),
  skipInteraction: (interactionId: string, chatSessionId: string) =>
    request<{ chat_session_id: string; artifact: ChatArtifact }>(
      "/api/chat/interactions/" + encodeURIComponent(interactionId) + "/skip",
      json({ chat_session_id: chatSessionId, answers: [] }),
    ),
  /** W1 E5：三阶段逐题生成（SSE，边出边收）。 */
  streamQuestionPipeline,
  /** W1 E7：某份资料上的划线（每条都带 resolution：exact / relocated / stale）。 */
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
  answerInteraction: (interactionId: string, chatSessionId: string, answers: Array<{ id: string; answer: string }>) =>
    request<{ chat_session_id: string; artifact: ChatArtifact }>(
      "/api/chat/interactions/" + encodeURIComponent(interactionId) + "/answer",
      json({ chat_session_id: chatSessionId, answers }),
    ),
  cancelRun: (streamId: string) =>
    request<{ ok: boolean; cancelled: boolean }>(
      "/api/chat/streams/" + encodeURIComponent(streamId) + "/cancel",
      { method: "POST" },
    ),
};
