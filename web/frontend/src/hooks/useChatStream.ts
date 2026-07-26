import { useState } from "react";

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
 */
export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState("");
  const [brandState, setBrandState] = useState<ProcessBrandState>("thinking");

  const updateLastMessage = (patch: (message: ChatMessage) => ChatMessage) => {
    setMessages((current) => current.map((item, index) => index === current.length - 1 ? patch(item) : item));
  };

  function handleStreamEvent(streamEvent: ChatStreamEvent, handlers: StreamEventHandlers = {}) {
    if (streamEvent.event === "run_started") {
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
      updateLastMessage((item) => ({ ...item, content: item.content + streamEvent.data.content }));
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
      if (artifact.type === "knowledge_context") handlers.onKnowledgeContext?.(artifact.context);
      updateLastMessage((item) => ({ ...item, artifacts: [...(item.artifacts || []), artifact] }));
    }
    if (streamEvent.event === "run_failed") throw new Error(streamEvent.data.error.message);
    if (streamEvent.event === "run_completed") {
      setBrandState("ready");
      setStatus("回答已经整理完成");
    }
  }

  /** Marks the trailing pending assistant message as settled (optionally failed). */
  function settleLastMessage(failed = false) {
    updateLastMessage((item) => failed ? { ...item, pending: false, failed: true } : { ...item, pending: false });
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
