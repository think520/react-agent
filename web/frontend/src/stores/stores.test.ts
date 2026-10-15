import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useChatStream } from "../hooks/useChatStream";
import { useHandoffStore } from "./handoffStore";
import { useUiStore } from "./uiStore";

describe("cross-page state stores", () => {
  beforeEach(() => {
    localStorage.clear();
    useHandoffStore.setState({
      practiceTopic: null,
      practiceWebResearchId: null,
      wikiScope: null,
      chatDraft: null,
    });
    useUiStore.setState({
      documentScope: [],
      strictDocumentScope: false,
      conceptDetailId: null,
      knowledgeContext: null,
      sourceContext: null,
    });
  });

  it("consumes a chat draft exactly once", () => {
    useHandoffStore.getState().setChatDraft("解释注意力机制");

    expect(useHandoffStore.getState().consumeChatDraft()).toBe("解释注意力机制");
    expect(useHandoffStore.getState().consumeChatDraft()).toBeNull();
  });

  it("deduplicates document scope and clears practice handoff together", () => {
    useUiStore.getState().setDocumentScope(["doc-1", "doc-1", "doc-2"]);
    useHandoffStore.getState().setPracticeTopic("Transformer");
    useHandoffStore.getState().setPracticeWebResearch("research-1");

    expect(useUiStore.getState().documentScope).toEqual(["doc-1", "doc-2"]);
    useHandoffStore.getState().clearPracticeHandoff();
    expect(useHandoffStore.getState().practiceTopic).toBeNull();
    expect(useHandoffStore.getState().practiceWebResearchId).toBeNull();
  });
});

describe("chat stream reducer", () => {
  it("reduces status, deltas, citations, and completion onto the pending message", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setMessages([{ role: "assistant", content: "", pending: true }]));

    act(() => result.current.handleStreamEvent({
      event: "status",
      data: { phase: "tool", message: "正在查找资料", tool_name: "rag_search" },
    }));
    act(() => result.current.handleStreamEvent({
      event: "message_delta",
      data: { content: "注意力机制" },
    }));
    act(() => result.current.handleStreamEvent({
      event: "citation",
      data: { attribution: { kind: "local", sources: [] } },
    }));
    act(() => result.current.handleStreamEvent({
      event: "run_completed",
      data: { chat_session_id: "session-1", termination_reason: "final_answer" },
    }));
    act(() => result.current.settleLastMessage());

    expect(result.current.messages[0]).toMatchObject({
      content: "注意力机制",
      pending: false,
      attribution: { kind: "local", sources: [] },
    });
    expect(result.current.messages[0].process?.[0].toolName).toBe("rag_search");
    expect(result.current.brandState).toBe("ready");
  });

  // W1 E11 / D4：过渡说明（narration）进"过程"，不进答案正文。
  it("keeps narration out of the answer body", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setMessages([{ role: "assistant", content: "", pending: true }]));

    act(() => result.current.handleStreamEvent({
      event: "message_delta",
      data: { content: "我先查一下资料。", call_role: "narration" },
    }));
    act(() => result.current.handleStreamEvent({
      event: "message_delta",
      data: { content: "极限的定义是……", call_role: "finish" },
    }));
    act(() => result.current.settleLastMessage());

    expect(result.current.messages[0].process?.at(-1)?.message).toBe("我先查一下资料。");
    expect(result.current.messages[0].content).not.toContain("我先查一下资料。");
    expect(result.current.messages[0].content).toContain("极限的定义是");
  });

  it("still appends a delta that carries no role", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setMessages([{ role: "assistant", content: "", pending: true }]));

    act(() => result.current.handleStreamEvent({ event: "message_delta", data: { content: "老路径" } }));
    act(() => result.current.settleLastMessage());

    expect(result.current.messages[0].content).toContain("老路径");
  });

  it("attaches the active session id to a practice artifact", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setMessages([{ role: "assistant", content: "", pending: true }]));
    const onKnowledgeContext = vi.fn();

    act(() => result.current.handleStreamEvent({
      event: "chat_artifact",
      data: {
        artifact: {
          artifact_id: "practice-1",
          type: "practice_ready",
          status: "ready",
          topic: "RAG",
          count: 5,
          question_ids: [1, 2, 3, 4, 5],
          attribution: { kind: "local", sources: [] },
        },
      },
    }, { getSessionId: () => "session-1", onKnowledgeContext }));

    expect(result.current.messages[0].artifacts?.[0]).toMatchObject({
      type: "practice_ready",
      chat_session_id: "session-1",
    });
    expect(onKnowledgeContext).not.toHaveBeenCalled();
  });
});
