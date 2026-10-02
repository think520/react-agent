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

  // W1 E4：multi_select 是路线里的承诺 —— 卡片必须真的能多选（旧实现点第二个会顶掉第一个）。
  it("keeps every pick for a multi_select question", () => {
    const onAnswer = vi.fn();
    const multi: AskUserArtifact = {
      ...artifact,
      questions: [{
        id: "q1", prompt: "这两章里想先学哪些？",
        options: ["极限", "导数", "积分"], multi_select: true,
      }],
    };
    render(<AskUserCard artifact={multi} busy={false} onAnswer={onAnswer} />);

    fireEvent.click(screen.getByRole("button", { name: "极限" }));
    fireEvent.click(screen.getByRole("button", { name: "积分" }));

    // 两个选项都保持选中（不是"点第二个顶掉第一个"）。
    expect(screen.getByRole("button", { name: "极限" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "积分" })).toHaveClass("active");

    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    const [, answers] = onAnswer.mock.calls[0];
    expect(answers).toHaveLength(1);
    // 后端按集合判分（逗号串或数组都能吃），这里钉住"两个值都在"。
    expect(answers[0].answer).toContain("极限");
    expect(answers[0].answer).toContain("积分");
  });

  it("still replaces the pick for a single-choice question", () => {
    const onAnswer = vi.fn();
    render(<AskUserCard artifact={artifact} busy={false} onAnswer={onAnswer} />);

    fireEvent.click(screen.getByRole("button", { name: "极限" }));
    fireEvent.click(screen.getByRole("button", { name: "导数" }));
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    expect(onAnswer).toHaveBeenCalledWith(artifact, [{ id: "q1", answer: "导数" }]);
  });

  // W1 E4：先不答也要有个明确的出口（后端会关闭交互并唤醒暂停的那一轮）。
  it("offers a skip action when the caller supports it", () => {
    const onSkip = vi.fn();
    render(<AskUserCard artifact={artifact} busy={false} onAnswer={() => {}} onSkip={onSkip} />);

    fireEvent.click(screen.getByRole("button", { name: "先不答，跳过" }));

    expect(onSkip).toHaveBeenCalledWith(artifact);
  });

  it("shows no skip button when the caller does not handle it", () => {
    render(<AskUserCard artifact={artifact} busy={false} onAnswer={() => {}} />);

    expect(screen.queryByRole("button", { name: "先不答，跳过" })).toBeNull();
  });

  it("shows the answers in place once resolved", () => {
    render(<AskUserCard artifact={{ ...artifact, status: "graded", answers: [{ id: "q1", answer: "导数" }] }} busy={false} onAnswer={() => {}} />);
    expect(screen.getByText("已回答")).toBeInTheDocument();
    expect(screen.getByText("导数")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交" })).toBeNull();
  });
});
