import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { createChatActions, type ChatActionContext } from "./chatActions";

function makeContext(overrides: Partial<ChatActionContext> = {}) {
  const setMessages = vi.fn();
  const context = {
    messages: [],
    setMessages,
    status: "",
    setStatus: vi.fn(),
    brandState: "thinking",
    setBrandState: vi.fn(),
    handleStreamEvent: vi.fn(),
    settleLastMessage: vi.fn(),
    truncated: null,
    clearTruncated: vi.fn(),
    settings: null,
    sessionId: "s1",
    navigate: vi.fn(),
    documents: [],
    selectedDocumentIds: [],
    referenceDocuments: [],
    inputRef: { current: null },
    abortRef: { current: null },
    streamIdRef: { current: null },
    sessionIdRef: { current: "s1" },
    leaveChatRef: { current: false },
    startDocumentImport: vi.fn(),
    documentImporting: false,
    openLibrarySetup: vi.fn(),
    clearDocumentScope: vi.fn(),
    selectedDocuments: [],
    resolveModelRef: () => "",
    sessionRef: () => "",
    setSelectedProvider: vi.fn(),
    setDraft: vi.fn(),
    draft: "",
    sending: false,
    webOnce: false,
    libraryReady: true,
    activeLibrary: { library_id: "library-1", name: "测试资料库", created_at: "", last_opened_at: "", active: true, available: true },
    pinToBottom: vi.fn(),
    references: [],
    webSelections: {},
    refreshSessions: vi.fn(async () => undefined),
    refreshSettings: vi.fn(async () => undefined),
    receiveKnowledgeContext: vi.fn(),
    selectedProvider: "",
    strictDocumentScope: false,
    ...overrides,
  };
  return { context: context as unknown as ChatActionContext, setMessages };
}

describe("createChatActions.startWebSearch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("echoes the /web search query immediately, before the request finishes", async () => {
    let resolveSearch: (value: unknown) => void = () => undefined;
    const pending = new Promise((resolve) => { resolveSearch = resolve; });
    vi.spyOn(api, "createWebSearch").mockReturnValue(pending as never);
    vi.spyOn(api, "session").mockResolvedValue({ messages: [] } as never);
    const { context, setMessages } = makeContext();

    const action = createChatActions(context).startWebSearch("测试工程师", undefined, true);
    expect(setMessages).toHaveBeenCalledTimes(1);
    const update = setMessages.mock.calls[0][0] as (messages: unknown[]) => unknown;
    expect(update([])).toEqual([{ role: "user", content: "测试工程师" }]);

    resolveSearch({ chat_session_id: "s1", artifact: { type: "web_candidates", status: "failed", candidates: [] } });
    await action;
  });
});

describe("createChatActions.applyWebCandidates", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("echoes the follow-up message before the selected pages finish loading", async () => {
    let resolveSelect: (value: unknown) => void = () => undefined;
    const pending = new Promise((resolve) => { resolveSelect = resolve; });
    vi.spyOn(api, "selectWebSources").mockReturnValue(pending as never);
    vi.spyOn(api, "session").mockResolvedValue({ messages: [] } as never);
    const { context, setMessages } = makeContext({ webSelections: { search1: ["candidate1"] } });

    const action = createChatActions(context).applyWebCandidates({
      type: "web_candidates",
      artifact_id: "a1",
      search_id: "search1",
      query: "测试工程师",
      status: "ready",
      candidates: [],
      created_at: "",
    } as never);
    expect(setMessages).toHaveBeenCalledTimes(1);
    const update = setMessages.mock.calls[0][0] as (messages: unknown[]) => unknown;
    expect(update([])).toEqual([{ role: "user", content: "使用选中的网页来源继续回答。" }]);

    resolveSelect({ artifact: { type: "web_evidence", status: "failed", research_id: "r1" } });
    await action;
  });
});
