import { useEffect, useRef, useState } from "react";

import type { ChatStreamEvent } from "../lib/api";
import type { ChatMessage, KnowledgeContext } from "../types";

export type ProcessBrandState = "thinking" | "reading" | "writing" | "ready";

export interface StreamEventHandlers {
  /** Called when the backend assigns/echoes the chat session id. */
  onRunStarted?: (chatSessionId: string) => void;
  /** Current session id used to tag practice_ready artifacts. */
  getSessionId?: () => string | undefined;
  /** Called when a knowledge_context artifact arrives. */
  onKnowledgeContext?: (context: KnowledgeContext) => void;
}

// 后端为证据门禁会先生成完整回答、再一次性回放所有 token，前端直接 append
// 会导致整段弹出（无打字机效果）。这里用缓冲区匀速 flush，模拟流式观感。
const FLUSH_CHARS_PER_TICK = 4;
const FLUSH_TICK_MS = 30;

/**
 * Owns the streaming chat surface state (messages, status line, brand state)
 * and reduces SSE events onto the pending assistant message.
 */
export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState("");
  const [brandState, setBrandState] = useState<ProcessBrandState>("thinking");

  const bufferRef = useRef("");
  const flushTimerRef = useRef<number | null>(null);

  const updateLastMessage = (patch: (message: ChatMessage) => ChatMessage) => {
    setMessages((current) => current.map((item, index) => index === current.length - 1 ? patch(item) : item));
  };

  const stopFlush = () => {
    if (flushTimerRef.current !== null) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  };

  const drainBuffer = () => {
    const remaining = bufferRef.current;
    bufferRef.current = "";
    stopFlush();
    if (remaining) {
      updateLastMessage((item) => ({ ...item, content: item.content + remaining }));
    }
  };

  const flushStep = () => {
    if (!bufferRef.current) {
      flushTimerRef.current = null;
      return;
    }
    const chunk = bufferRef.current.slice(0, FLUSH_CHARS_PER_TICK);
    bufferRef.current = bufferRef.current.slice(FLUSH_CHARS_PER_TICK);
    if (chunk) {
      updateLastMessage((item) => ({ ...item, content: item.content + chunk }));
    }
    flushTimerRef.current = window.setTimeout(flushStep, FLUSH_TICK_MS);
  };

  const enqueueDelta = (text: string) => {
    bufferRef.current += text;
    if (flushTimerRef.current === null) {
      flushTimerRef.current = window.setTimeout(flushStep, FLUSH_TICK_MS);
    }
  };

  useEffect(() => () => { stopFlush(); bufferRef.current = ""; }, []);

  function handleStreamEvent(streamEvent: ChatStreamEvent, handlers: StreamEventHandlers = {}) {
    if (streamEvent.event === "run_started") {
      bufferRef.current = "";
      stopFlush();
      handlers.onRunStarted?.(streamEvent.data.chat_session_id);
    }
    if (streamEvent.event === "status") {
      setStatus(streamEvent.data.message);
      if (["rag_search", "web_research"].includes(streamEvent.data.tool_name || "") || /资料|检索|查找|读取|网页/.test(streamEvent.data.message)) setBrandState("reading");
      else if (["question_generate", "quiz_start"].includes(streamEvent.data.tool_name || "") || /题目|练习|生成/.test(streamEvent.data.message)) setBrandState("writing");
      updateLastMessage((item) => ({
        ...item,
        process: [...(item.process || []), {
          phase: streamEvent.data.phase,
          message: streamEvent.data.message,
          toolName: streamEvent.data.tool_name,
          elapsed: streamEvent.data.elapsed,
        }],
      }));
    }
    if (streamEvent.event === "message_delta") {
      setStatus("正在组织回答");
      setBrandState("writing");
      enqueueDelta(streamEvent.data.content);
    }
    if (streamEvent.event === "citation") {
      setStatus("已找到相关资料，正在整理");
      setBrandState("reading");
      updateLastMessage((item) => ({ ...item, attribution: streamEvent.data.attribution }));
    }
    if (streamEvent.event === "personalization") {
      updateLastMessage((item) => ({ ...item, personalization: streamEvent.data.references }));
    }
    if (streamEvent.event === "chat_artifact") {
      const artifact = streamEvent.data.artifact.type === "practice_ready"
        ? { ...streamEvent.data.artifact, chat_session_id: handlers.getSessionId?.() }
        : streamEvent.data.artifact;
      if (artifact.type === "knowledge_context") {
        handlers.onKnowledgeContext?.(artifact.context);
        // 一轮内多次 concept_map_query 只保留第一张概念卡片，避免重复
        updateLastMessage((item) => {
          if ((item.artifacts || []).some((existing) => existing.type === "knowledge_context")) return item;
          return { ...item, artifacts: [...(item.artifacts || []), artifact] };
        });
      } else {
        updateLastMessage((item) => ({ ...item, artifacts: [...(item.artifacts || []), artifact] }));
      }
    }
    if (streamEvent.event === "run_failed") throw new Error(streamEvent.data.error.message);
    if (streamEvent.event === "run_completed") {
      drainBuffer();
      setBrandState("ready");
      setStatus("回答已经整理完成");
    }
  }

  /** Marks the trailing pending assistant message as settled (optionally failed or user-stopped). */
  function settleLastMessage(failed = false, stopped = false) {
    drainBuffer();
    updateLastMessage((item) => {
      if (failed) return { ...item, pending: false, failed: true };
      if (stopped) return { ...item, pending: false, stopped: true };
      return { ...item, pending: false };
    });
  }

  return {
    messages,
    setMessages,
    status,
    setStatus,
    brandState,
    setBrandState,
    handleStreamEvent,
    settleLastMessage,
  };
}
