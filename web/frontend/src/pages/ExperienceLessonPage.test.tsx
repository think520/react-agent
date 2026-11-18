import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExperienceLessonPage } from "./ExperienceLessonPage";

const navigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate };
});

beforeEach(() => {
  window.localStorage.clear();
  navigate.mockReset();
});

afterEach(cleanup);

describe("ExperienceLessonPage", () => {
  it("offers a source location and checks the bundled quiz without a backend", () => {
    render(<ExperienceLessonPage />);

    expect(screen.getByText(/示例内容，不写入你的资料库/)).toBeTruthy();
    expect(document.getElementById("experience-source-detail")?.textContent).toContain("RAG 会先从资料中检索与问题相关的片段");
    expect(screen.getByRole("link", { name: /去做一道离线题/ })).toHaveAttribute("href", "#experience-question");

    fireEvent.click(screen.getByDisplayValue("B"));
    fireEvent.click(screen.getByRole("button", { name: /检查答案/ }));
    expect(screen.getByText("答对了")).toBeTruthy();
    expect(screen.getByRole("link", { name: /回到讲义原文/ })).toHaveAttribute("href", "#experience-source-detail");
    expect(window.localStorage.getItem("bobodan:experience-lesson:v1")).toContain('"completed":true');
  });

  it("restores an unfinished answer when the learner returns", () => {
    window.localStorage.setItem("bobodan:experience-lesson:v1", JSON.stringify({ answer: "A", completed: false }));
    render(<ExperienceLessonPage />);

    expect(screen.getByDisplayValue("A")).toBeChecked();
    expect(screen.getByRole("button", { name: /检查答案/ })).toBeEnabled();
  });
});
