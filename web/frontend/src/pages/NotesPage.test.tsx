import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { NotesPage } from "./NotesPage";

const hoisted = vi.hoisted(() => ({ ctx: {} as Record<string, unknown> }));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useOutletContext: () => hoisted.ctx };
});

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      memoryKnowledge: vi.fn(),
      createMemoryKnowledge: vi.fn(),
      updateMemoryKnowledge: vi.fn(),
      deleteMemoryKnowledge: vi.fn(),
    },
  };
});

function renderPage() {
  return render(<MemoryRouter><NotesPage /></MemoryRouter>);
}

beforeEach(() => {
  localStorage.clear();
  hoisted.ctx = {
    documents: [],
    activeLibrary: { library_id: "lib-1", name: "测试资料库", available: true },
    settings: { preferences: { memory: { enabled: true } } },
  };
  vi.mocked(api.memoryKnowledge).mockResolvedValue({ items: [] });
  vi.mocked(api.createMemoryKnowledge).mockResolvedValue({ item: {} } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

describe("NotesPage drafts", () => {
  it("restores an unsaved draft after leaving the page", async () => {
    const first = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "写笔记" }));
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), {
      target: { value: "# 向量检索\n\n这是还没有保存的理解。" },
    });
    first.unmount();

    renderPage();

    await waitFor(() => expect(screen.getByRole("textbox", { name: "笔记正文" }))
      .toHaveValue("# 向量检索\n\n这是还没有保存的理解。"));
  });

  it("clears the local draft after a successful save", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "写笔记" }));
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), {
      target: { value: "# 标题\n\n正文" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));

    await waitFor(() => expect(api.createMemoryKnowledge).toHaveBeenCalled());
    expect(localStorage.getItem("bobodan:note-draft:lib-1")).toBeNull();
  });

  it("shows the 5000 character limit before the backend can reject the note", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "写笔记" }));
    fireEvent.change(screen.getByRole("textbox", { name: "笔记正文" }), {
      target: { value: "# 标题\n\n" + "字".repeat(5001) },
    });

    expect(screen.getByText(/5001\/5000/)).toHaveClass("over-limit");
    expect(screen.getByRole("button", { name: "保存笔记" })).toBeDisabled();
    expect(api.createMemoryKnowledge).not.toHaveBeenCalled();
  });
});
