import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useHandoffStore } from "../stores/handoffStore";
import { ChatPage } from "./ChatPage";

const hoisted = vi.hoisted(() => ({ ctx: {} as Record<string, unknown> }));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useOutletContext: () => hoisted.ctx };
});

function shellContext() {
  return {
    refreshSessions: vi.fn().mockResolvedValue(undefined),
    refreshSettings: vi.fn().mockResolvedValue(null),
    sessions: [],
    settings: null,
    documents: [],
    selectedDocumentIds: [],
    selectedDocuments: [],
    openContext: vi.fn(),
    openConceptDetail: vi.fn(),
    showKnowledgeContext: vi.fn(),
    receiveKnowledgeContext: vi.fn(),
    clearKnowledgeContext: vi.fn(),
    showSourceContext: vi.fn(),
    clearDocumentScope: vi.fn(),
    activeLibrary: null,
    openLibrarySetup: vi.fn(),
    startDocumentImport: vi.fn(),
    documentImporting: false,
    libraryReady: true,
  };
}

beforeEach(() => {
  localStorage.clear();
  useHandoffStore.setState({ chatDraft: null });
  hoisted.ctx = shellContext();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("ChatPage initialization", () => {
  it("keeps an in-memory draft when settings finish loading", async () => {
    const view = render(<MemoryRouter><ChatPage /></MemoryRouter>);
    const composer = screen.getByRole("textbox", { name: "消息" });

    fireEvent.change(composer, { target: { value: "帮我安排学习路线" } });
    localStorage.removeItem("bobodan:draft:new");

    hoisted.ctx.settings = {
      default_provider: "deepseek",
      providers: [{ name: "deepseek", configured: true, model: "deepseek-chat" }],
      skills: [],
      preferences: {
        revision: 0,
        assistant: { display_name: "Bobodan", answer_depth: "standard" },
        memory: { enabled: true },
      },
    };
    view.rerender(<MemoryRouter><ChatPage /></MemoryRouter>);

    await waitFor(() => expect(composer).toHaveValue("帮我安排学习路线"));
  });
});
