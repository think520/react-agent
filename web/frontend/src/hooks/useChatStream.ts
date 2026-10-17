import { useCallback, useEffect, useReducer, useRef } from "react";

import { StreamBuffer } from "../lib/streamBuffer";
import { prefersReducedMotion } from "../lib/motion";
import type { ChatStreamEvent } from "../lib/api";
import type { ChatStreamEventKind } from "../lib/chatStreamEvents";
import {
  foldChatStream,
  initialChatStreamState,
  isStaleSeq,
  rememberSeq,
  streamEffects,
  type ChatFoldInput,
  type ChatStreamState,
  type ProcessBrandState,
} from "../lib/chatFold";
import type { ChatMessage, KnowledgeContext } from "../types";

export type { ProcessBrandState } from "../lib/chatFold";

export interface StreamEventHandlers {
  /** Called when the backend assigns/echoes the chat session id. */
  onRunStarted?: (chatSessionId: string) => void;
  /** Current session id used to tag practice_ready artifacts. */
  getSessionId?: () => string | undefined;
  /** Called when a knowledge_context artifact arrives. */
  onKnowledgeContext?: (context: KnowledgeContext) => void;
}

/**
 * W3 F3 保留的「明确忽略」机制。
 *
 * 2026-10-17：原来这里登记了 `practice` / `learning_update` —— 后端没有生产者、前端没有消费者，
 * 已从服务端适配器（`web/backend/events.py`）和前端 union（`lib/chatStreamEvents.ts`）一并删除。
 * 保留空表，是为了以后真出现「收到了但决定不处理」的事件时，仍有一个**必须写明理由**的位置
 * （`hooks/useChatStream.test.ts` 会为每个事件名逼问一次：改变了状态，还是被明确忽略？）。
 */
export const IGNORED_STREAM_EVENTS: Partial<Record<ChatStreamEventKind, string>> = {};

/**
 * 流式聊天界面状态的**适配层**（W3 F1）。
 *
 * 归约逻辑本身已经搬进 `lib/chatFold.ts` 的纯函数；这里只做三件事：
 * 1) 把事件喂给 reducer（**唯一入口** `applyEvent`，也就是 `handleStreamEvent`）；
 * 2) 在**入打字机缓冲之前**丢掉重放帧（用同一份 `isStaleSeq` —— 否则重放会被缓冲后
 *    作为已刷新内容追加，正文照样写两遍）；
 * 3) 执行纯函数无法执行的副作用（会话 id、知识上下文回调、缓冲器）。
 */
export function useChatStream() {
  const [state, rawDispatch] = useReducer(foldChatStream, initialChatStreamState);
  const bufferRef = useRef<StreamBuffer | null>(null);
  //: reducer 是纯函数，所以这里能同步镜像出「下一次的状态」——
  //: setMessages 的 updater 形式需要立刻读到最新消息，不能等一次渲染。
  const stateRef = useRef<ChatStreamState>(state);
  //: 已应用的帧序号（与 reducer 里的那份同步推进），用于在入缓冲前判重放。
  const appliedSeqRef = useRef<Record<string, number>>({});

  const dispatch = useCallback((input: ChatFoldInput) => {
    stateRef.current = foldChatStream(stateRef.current, input);
    rawDispatch(input);
  }, []);

  const ensureBuffer = useCallback(() => {
    if (!bufferRef.current) {
      // Live provider: honoring the in-app reduced-motion toggle mid-session
      // requires re-evaluating on every flush, not once at mount.
      bufferRef.current = new StreamBuffer(
        (chunk) => dispatch({ kind: "delta-flush", content: chunk }),
        { reducedMotion: prefersReducedMotion },
      );
    }
    return bufferRef.current;
  }, [dispatch]);

  const resetBuffer = useCallback(() => {
    bufferRef.current?.reset();
    bufferRef.current = null;
  }, []);

  const drainBuffer = useCallback(() => bufferRef.current?.drain(), []);

  useEffect(() => () => resetBuffer(), [resetBuffer]);

  const applyEvent = useCallback((streamEvent: ChatStreamEvent, handlers: StreamEventHandlers = {}) => {
    // 重放（断线重连会重发）在任何副作用之前丢掉。
    if (isStaleSeq(appliedSeqRef.current, streamEvent)) return;
    appliedSeqRef.current = rememberSeq(appliedSeqRef.current, streamEvent);

    const effects = streamEffects(streamEvent);
    if (effects.sessionId) handlers.onRunStarted?.(effects.sessionId);
    if (effects.knowledgeContext) handlers.onKnowledgeContext?.(effects.knowledgeContext);

    if (streamEvent.event === "run_started") resetBuffer();
    if (streamEvent.event === "run_completed") drainBuffer();
    if (streamEvent.event === "run_failed") {
      dispatch({ kind: "stream", event: streamEvent, sessionId: handlers.getSessionId?.() });
      throw new Error(streamEvent.data.error.message);
    }
    if (streamEvent.event === "message_delta" && streamEvent.data.call_role !== "narration") {
      // 正文走打字机缓冲；过程说明（narration）直接进过程列表。
      ensureBuffer().push(streamEvent.data.content);
    }
    dispatch({ kind: "stream", event: streamEvent, sessionId: handlers.getSessionId?.() });
  }, [dispatch, drainBuffer, ensureBuffer, resetBuffer]);

  /** 原来的名字，保留给已有调用方；语义就是 applyEvent。 */
  const handleStreamEvent = applyEvent;

  /** Marks the trailing pending assistant message as settled (optionally failed or user-stopped). */
  const settleLastMessage = useCallback((failed = false, stopped = false) => {
    drainBuffer();
    dispatch({ kind: "settle", failed, stopped });
  }, [dispatch, drainBuffer]);

  const setMessages = useCallback((next: ChatMessage[] | ((current: ChatMessage[]) => ChatMessage[])) => {
    const messages = typeof next === "function" ? next(stateRef.current.messages) : next;
    dispatch({ kind: "replace-messages", messages });
  }, [dispatch]);

  const setStatus = useCallback((status: string) => dispatch({ kind: "set-status", status }), [dispatch]);
  const setBrandState = useCallback(
    (brandState: ProcessBrandState) => dispatch({ kind: "set-brand", brandState }),
    [dispatch],
  );
  const clearTruncated = useCallback(() => dispatch({ kind: "clear-truncated" }), [dispatch]);

  return {
    messages: state.messages,
    setMessages,
    status: state.status,
    setStatus,
    brandState: state.brandState,
    setBrandState,
    handleStreamEvent,
    applyEvent,
    settleLastMessage,
    truncated: state.truncated,
    clearTruncated,
  };
}