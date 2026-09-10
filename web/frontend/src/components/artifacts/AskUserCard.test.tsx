import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AskUserArtifact } from "../../types";
import { AskUserCard } from "./AskUserCard";

const artifact: AskUserArtifact = {
  type: "ask_user",
  artifact_id: "i1",
  status: "awaiting_input",
  questions: [{ id: "q1", prompt: "先学哪个主题？", options: ["极限", "导数"] }],
};

afterEach(cleanup);

describe("AskUserCard", () => {
  it("keeps submit disabled until every question is answered", () => {
    render(<AskUserCard artifact={artifact} busy={false} onAnswer={() => {}} />);
    expect(screen.getByRole("button", { name: "提交" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "极限" }));
    expect(screen.getByRole("button", { name: "提交" })).not.toBeDisabled();
  });

  it("submits the chosen option", () => {
    const onAnswer = vi.fn();
    render(<AskUserCard artifact={artifact} busy={false} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByRole("button", { name: "导数" }));
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
    expect(onAnswer).toHaveBeenCalledWith(artifact, [{ id: "q1", answer: "导数" }]);
  });

  it("shows the answers in place once resolved", () => {
    render(<AskUserCard artifact={{ ...artifact, status: "graded", answers: [{ id: "q1", answer: "导数" }] }} busy={false} onAnswer={() => {}} />);
    expect(screen.getByText("已回答")).toBeInTheDocument();
    expect(screen.getByText("导数")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交" })).toBeNull();
  });
});
