/**
 * W3 F1：流式事件的**纯归约**（从 useChatStream 里搬出来）。
 *
 * 三件事：
 * 1) 归约逻辑不再埋在 hook 里 —— 它是流式正确性的根，必须能直接测；
 * 2) 对 `seq` **幂等**：断线重连会把帧重放一次，重放必须被丢弃，而不是把回答写两遍；
 * 3) 副作用（会话 id、知识上下文回调）不在这里做 —— `streamEffects` 只**读出**它们，
 *    由 hook 执行，这样这个模块可以保持纯函数。
 */

import type { ChatStreamEvent } from "./api";
import type { ChatMessage, KnowledgeContext } from "../types";

export type ProcessBrandState = "thinking" | "reading" | "writing" | "ready";

export interface ChatStreamState {
  messages: ChatMessage[];
  status: string;
  brandState: ProcessBrandState;
  truncated: { continuing: boolean } | null;
  /** seq 幂等：每个 stream 已应用到第几号（换 stream_id 就重新开始）。 */
  lastSeqByStream: Record<string, number>;
}

export const initialChatStreamState: ChatStreamState = {
  messages: [],
  status: "",
  brandState: "thinking",
  truncated: null,
  lastSeqByStream: {},
};

export type ChatFoldInput =
  | { kind: "stream"; event: ChatStreamEvent; sessionId?: string }
  | { kind: "delta-flush"; content: string }
  | { kind: "replace-messages"; messages: ChatMessage[] }
  | { kind: "set-status"; status: string }
  | { kind: "set-brand"; brandState: ProcessBrandState }
  | { kind: "clear-truncated" }
  | { kind: "settle"; failed?: boolean; stopped?: boolean };

export interface StreamEffects {
  sessionId?: string;
  knowledgeContext?: KnowledgeContext;
}

/** 从一帧里读出需要执行**副作用**的部分（纯读，不执行）。 */
export function streamEffects(event: ChatStreamEvent): StreamEffects {
  if (event.event === "run_started") {
    return { sessionId: event.data.chat_session_id };
  }
  if (event.event === "chat_artifact" && event.data.artifact.type === "knowledge_context") {
    return { knowledgeContext: event.data.artifact.context };
  }
  return {};
}

function patchLast(state: ChatStreamState, patch: (message: ChatMessage) => ChatMessage): ChatStreamState {
  if (state.messages.length === 0) return state;
  const index = state.messages.length - 1;
  const current = state.messages[index];
  const next = patch(current);
  if (next === current) return state; // 没变就不换对象
  const messages = state.messages.slice();
  messages[index] = next;
  return { ...state, messages };
}

function pushProcess(
  state: ChatStreamState,
  entry: { phase: string; message: string; toolName?: string; elapsed?: number },
): ChatStreamState {
  return patchLast(state, (message) => ({
    ...message,
    process: [...(message.process || []), entry],
  }));
}

/**
 * 这一帧是不是重放（序号不比已应用的更新）→ 应当丢弃。
 *
 * 导出成纯函数是**故意**的：hook 必须在把 delta 交给打字机缓冲**之前**就用它判断 ——
 * 否则重放会被缓冲一遍，稍后作为「已刷新」追加进去，正文还是写两遍（去重就白做了）。
 */
export function isStaleSeq(applied: Record<string, number>, event: ChatStreamEvent): boolean {
  const meta = event.data as { seq?: number; stream_id?: string };
  const seq = typeof meta.seq === "number" ? meta.seq : null;
  if (seq === null) return false; // 没有序号就不去重（老服务端/夹具）
  const streamId = String(meta.stream_id || "");
  const seen = applied[streamId];
  return seen !== undefined && seq <= seen;
}

/** 记下这一帧的序号（同样给 hook 用，保证两边看到的是同一份进度）。 */
export function rememberSeq(applied: Record<string, number>, event: ChatStreamEvent): Record<string, number> {
  const meta = event.data as { seq?: number; stream_id?: string };
  const seq = typeof meta.seq === "number" ? meta.seq : null;
  if (seq === null) return applied;
  const streamId = String(meta.stream_id || "");
  return { ...applied, [streamId]: seq };
}

export function foldChatStream(state: ChatStreamState, input: ChatFoldInput): ChatStreamState {
  if (input.kind === "replace-messages") return { ...state, messages: input.messages };
  if (input.kind === "set-status") return { ...state, status: input.status };
  if (input.kind === "set-brand") return { ...state, brandState: input.brandState };
  if (input.kind === "clear-truncated") return state.truncated === null ? state : { ...state, truncated: null };
  if (input.kind === "delta-flush") {
    return patchLast(
      state,
      (message) => ({ ...message, content: message.content + input.content }),
    );
  }
  if (input.kind === "settle") {
    return patchLast(state, (message) => {
      if (input.failed) return { ...message, pending: false, failed: true };
      if (input.stopped) return { ...message, pending: false, stopped: true };
      return { ...message, pending: false };
    });
  }

  const event = input.event;
  if (isStaleSeq(state.lastSeqByStream, event)) return state;
  const nextSeqs = event.event === "run_failed" ? state.lastSeqByStream : rememberSeq(state.lastSeqByStream, event);
  // 序号表没变就不换对象 —— 明确忽略的事件应当原样返回，避免多余渲染。
  const applied = nextSeqs === state.lastSeqByStream ? state : { ...state, lastSeqByStream: nextSeqs };

  if (event.event === "run_started") return applied;

  if (event.event === "status") {
    const data = event.data;
    const toolName = data.tool_name || "";
    const reading = ["rag_search", "web_research"].includes(toolName)
      || /资料|检索|查找|读取|网页/.test(data.message);
    const writing = ["question_generate", "quiz_start"].includes(toolName)
      || /题目|练习|生成/.test(data.message);
    return pushProcess(
      {
        ...applied,
        status: data.message,
        brandState: reading ? "reading" : writing ? "writing" : applied.brandState,
      },
      { phase: data.phase, message: data.message, toolName: data.tool_name, elapsed: data.elapsed },
    );
  }

  if (event.event === "message_delta") {
    const withStatus = { ...applied, status: "正在组织回答", brandState: "writing" as ProcessBrandState };
    if (event.data.call_role === "narration") {
      // 调工具前的过渡说明进过程，不进最终答案正文。
      return pushProcess(withStatus, { phase: "narration", message: event.data.content });
    }
    return withStatus; // 正文由 delta-flush 追加（打字机缓冲在 hook 里）
  }

  if (event.event === "answer_truncated") {
    return {
      ...applied,
      truncated: { continuing: Boolean(event.data.continuing) },
      status: event.data.continuing ? "回答被长度上限截断，正在接着写" : "回答被长度上限截断",
    };
  }

  if (event.event === "citation") {
    return patchLast(
      { ...applied, status: "已找到相关资料，正在整理", brandState: "reading" },
      (message) => ({ ...message, attribution: event.data.attribution }),
    );
  }

  if (event.event === "personalization") {
    return patchLast(applied, (message) => ({ ...message, personalization: event.data.references }));
  }

  if (event.event === "chat_artifact") {
    const artifact = event.data.artifact.type === "practice_ready"
      ? { ...event.data.artifact, chat_session_id: input.sessionId }
      : event.data.artifact;
    if (artifact.type === "knowledge_context") {
      return patchLast(applied, (message) => {
        // 一轮内多次 concept_map_query 只保留第一张概念卡片。
        if ((message.artifacts || []).some((existing) => existing.type === "knowledge_context")) {
          return message;
        }
        return { ...message, artifacts: [...(message.artifacts || []), artifact] };
      });
    }
    return patchLast(applied, (message) => ({
      ...message,
      artifacts: [...(message.artifacts || []), artifact],
    }));
  }

  if (event.event === "run_completed") {
    return { ...applied, brandState: "ready", status: "回答已经整理完成" };
  }

  // run_failed 由调用方抛错（见 hook）；明确忽略的事件（practice / learning_update）到不了这里
  // 也会原样返回 —— 两种情况下状态对象都不换，避免多余渲染。
  return applied;
}
