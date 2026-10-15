import { useEffect, useRef, useState } from "react";

import { StreamBuffer } from "../lib/streamBuffer";
import { prefersReducedMotion } from "../lib/motion";
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

/**
 * Owns the streaming chat surface state (messages, status line, brand state)
 * and reduces SSE events onto the pending assistant message.
 *
 * The backend evidence gate replays a full answer as a burst of deltas; a
 * 30fps StreamBuffer flushes those into a typewriter-like effect (FE-2).
 */
export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState("");
  const [brandState, setBrandState] = useState<ProcessBrandState>("thinking");
  // W1 E11：这次回答有没有被输出上限截断（续写中 / 续写用尽）。
  const [truncated, setTruncated] = useState<{ continuing: boolean } | null>(null);

  const bufferRef = useRef<StreamBuffer | null>(null);

  const updateLastMessage = (patch: (message: ChatMessage) => ChatMessage) => {
    setMessages((current) => current.map((item, index) => index === current.length - 1 ? patch(item) : item));
  };

  const ensureBuffer = () => {
    if (!bufferRef.current) {
      // Live provider: honoring the in-app reduced-motion toggle mid-session
      // requires re-evaluating on every flush, not once at mount.
      bufferRef.current = new StreamBuffer(
        (chunk) => updateLastMessage((item) => ({ ...item, content: item.content + chunk })),
        { reducedMotion: prefersReducedMotion },
      );
    }
    return bufferRef.current;
  };

  const resetBuffer = () => {
    bufferRef.current?.reset();
    bufferRef.current = null;
  };

  const drainBuffer = () => bufferRef.current?.drain();

  const enqueueDelta = (text: string) => ensureBuffer().push(text);

  useEffect(() => () => resetBuffer(), []);

  function handleStreamEvent(streamEvent: ChatStreamEvent, handlers: StreamEventHandlers = {}) {
    if (streamEvent.event === "run_started") {
      resetBuffer();
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
      if (streamEvent.data.call_role === "narration") {
        // W1 E11 / D4：调工具前的过渡说明进"过程"，不进最终答案正文。
        updateLastMessage((item) => ({
          ...item,
          process: [...(item.process || []), { phase: "narration", message: streamEvent.data.content }],
        }));
        return;
      }
      enqueueDelta(streamEvent.data.content);
    }
    if (streamEvent.event === "answer_truncated") {
      // 续写中不打断用户；只有"续写用尽仍被截断"才提示，并给一个接着写的入口。
      setTruncated({ continuing: Boolean(streamEvent.data.continuing) });
      setStatus(streamEvent.data.continuing ? "回答被长度上限截断，正在接着写" : "回答被长度上限截断");
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
    truncated,
    clearTruncated: () => setTruncated(null),
  };
}
