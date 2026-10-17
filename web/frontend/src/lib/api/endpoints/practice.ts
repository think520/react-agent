/** practice 域的 API 方法（2026-10-17 从 lib/api.ts 逐块搬出，行为不变）。 */
import { json, request } from "../http";
import { } from "../transport";
import type {
  Attribution,
  PracticeSession,
  PracticeReadyArtifact,
  Question,
  QuestionBank,
  QuestionSetSummary,
  ReviewQueue,
  PersonalizationRef,








} from "../../../types";
import type { } from "../../chatStreamEvents";
import type {


} from "../types";
import type { } from "../transport";

export const practiceApi = {
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
};
