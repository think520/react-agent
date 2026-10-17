/** 流式与原文/资源访问（2026-10-17 从 lib/api.ts 抽出；库作用域统一走 getActiveLibraryId()）。 */
import type {
  ChatReference,
} from "../../types";
import type {  } from "../chatStreamEvents";
import { ApiError, getActiveLibraryId, json, type ErrorEnvelope } from "./http";
import type { ChatStreamEvent } from "./types";

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
    headers: getActiveLibraryId() ? { "X-Bobodan-Library-ID": getActiveLibraryId() } : undefined,
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
/**
 * Download the original file with its real name.
 *
 * Word and PowerPoint files have no in-page renderer, so the honest options are
 * "download it" or "open it with the system app" - both start here, and neither
 * pretends the browser can lay the document out.
 */
export async function downloadDocumentRaw(documentId: string, filename: string): Promise<void> {
  const response = await fetch(documentRawUrl(documentId), {
    headers: getActiveLibraryId() ? { "X-Bobodan-Library-ID": getActiveLibraryId() } : undefined,
  });
  if (!response.ok) {
    throw new ApiError(
      "无法取回原件 (" + response.status + ")",
      "document_raw_unavailable",
      response.status,
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || documentId;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // The download needs the URL until it starts; revoke lazily.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}


export function documentRawEmbedUrl(documentId: string): string {
  const base = documentRawUrl(documentId);
  return getActiveLibraryId() ? base + "?library=" + encodeURIComponent(getActiveLibraryId()) : base;
}


export function documentAssetUrl(documentId: string, source: string): string {
  if (!source || /^(https?:|data:|blob:|\/)/i.test(source)) return source;
  const base =
    "/api/kb/documents/" + encodeURIComponent(documentId) + "/asset?path=" + encodeURIComponent(source);
  return getActiveLibraryId() ? base + "&library=" + encodeURIComponent(getActiveLibraryId()) : base;
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
      headers: getActiveLibraryId() ? { "X-Bobodan-Library-ID": getActiveLibraryId() } : undefined,
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

/** W1 E5：三阶段管线的 SSE 事件。 */
export type QuestionPipelineEvent =
  | { event: "pipeline_started"; topic: string; count: number }
  | { event: "explore_done"; chunks: number }
  | { event: "quiz_plan"; source: string; plan: Array<{ topic: string; question_type?: string; difficulty?: string }> }
  | { event: "quiz_question_emitted"; index: number; total: number; question_id: number; topic?: string; question?: {
      id: number; question: string; type?: string; options?: string[];
      /** W1 E5：实时卡片要显示的字段。 */
      difficulty?: string; concepts?: string[];
    } }
  | { event: "quiz_question_failed"; index: number; total: number; topic?: string }
  | { event: "pipeline_done"; question_ids: number[]; total: number }
  | { event: "pipeline_cancelled"; emitted: number; total: number }
  | { event: "pipeline_failed"; code?: string; error?: string }
  | { event: "pipeline_result"; ok?: boolean; question_ids?: number[]; plan_source?: string };

/** W1 E5：逐题生成并**边出边收**（每题一帧，不等整批）。 */
export async function streamQuestionPipeline(
  body: { topic: string; count?: number; document_ids?: string[]; course?: string },
  onEvent: (event: QuestionPipelineEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/quiz/pipeline/stream", {
    ...json({
      topic: body.topic,
      count: body.count ?? 5,
      document_ids: body.document_ids ?? [],
      // W1 E5：课程范围可选（界面暂时只发资料范围）。
      ...(body.course ? { course: body.course } : {}),
    }),
    signal,
  });
  if (!response.ok || !response.body) {
    let error: ErrorEnvelope = {};
    try {
      error = (await response.json()) as ErrorEnvelope;
    } catch {
      // Non-JSON error bodies keep the generic message below.
    }
    throw new ApiError(
      error.error?.message || `无法开始逐题生成 (${response.status})`,
      error.error?.code || "pipeline_unavailable",
      response.status,
      error.error?.details,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line; a partial tail stays in the buffer.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        try {
          onEvent(JSON.parse(line.slice("data: ".length)) as QuestionPipelineEvent);
        } catch {
          // A malformed frame must not kill the stream.
        }
      }
    }
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
    /** F05: replay the persisted failed turn without duplicating its user message. */
    retryFailed?: boolean;
    /** W1 E14: session category — "chat" (default) | "practice" | "review". Only
     * stamped when the session is created, so tutor sessions stay out of the main list. */
    sessionKind?: "chat" | "practice" | "review";
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
      retry_failed: preferences.retryFailed ?? false,
      chat_session_id: chatSessionId || null,
      kind: preferences.sessionKind || "chat",
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
    headers: getActiveLibraryId() ? {
      "Content-Type": "application/json",
      "X-Bobodan-Library-ID": getActiveLibraryId(),
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
  let terminal: "completed" | "failed" | null = null;
  let terminalError: unknown = null;
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
    if (parsed.event === "run_completed") terminal = "completed";
    if (parsed.event === "run_failed") {
      terminal = "failed";
      terminalError = new ApiError(
        parsed.data.error.message || "AI 运行失败，请重试。",
        parsed.data.error.code || "chat_run_failed",
        0,
      );
    }
    try {
      onEvent(parsed);
    } catch (error) {
      if (parsed.event === "run_failed") terminalError = error;
      else throw error;
    }
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

  // A stream is complete only after an explicit terminal event. A clean EOF
  // without one is an interrupted protocol and must try the event log.
  if (!terminal && streamId) {
    if (networkError == null) {
      networkError = new ApiError(
        "对话连接提前结束，请重试。",
        "chat_stream_incomplete",
        0,
      );
    }
    for (const delay of RESUME_DELAYS_MS) {
      if (terminal) break;
      await sleep(delay);
      const body = await openResume(streamId, lastSeq);
      if (!body) continue;
      try {
        await pump(body);
      } catch (error) {
        // This attempt broke too: keep the remaining delays instead of giving
        // up on the run after the first unlucky reconnect.
        if (signal?.aborted) throw error;
        networkError = error;
        continue;
      }
    }
  }
  if (terminal === "failed") throw terminalError;
  // Nothing resumed and nothing terminal: report the original failure instead
  // of returning a silently truncated answer.
  if (!terminal) {
    throw networkError || new ApiError(
      "对话连接提前结束，请重试。",
      "chat_stream_incomplete",
      0,
    );
  }
}

