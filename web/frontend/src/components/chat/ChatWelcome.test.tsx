import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ProcessBrandState } from "../../hooks/useChatStream";
import type { ReviewQueue } from "../../types";
import { ChatWelcome } from "./ChatWelcome";

const emptyQueue: ReviewQueue = { due_concepts: [], wrong_answers: [], weaknesses: [] };

describe("ChatWelcome", () => {
  it("shows and dispatches the primary action selected from learning state", () => {
    const onPrimaryAction = vi.fn();
    render(<ChatWelcome
      libraryName="课程"
      error=""
      composer={null}
      wikiPlanLoading={false}
      status={null}
      brandState={"ready" as ProcessBrandState}
      documentImporting={false}
      documents={[]}
      review={{ ...emptyQueue, due_concepts: [{}] }}
      reviewStatus="ready"
      activePractices={[]}
      activePracticeStatus="ready"
      onApplyPrompt={vi.fn()}
      onImport={vi.fn()}
      onOpenPractice={vi.fn()}
      onOpenExperience={vi.fn()}
      onPrimaryAction={onPrimaryAction}
    />);

    fireEvent.click(screen.getByRole("button", { name: "开始今日复习" }));
    expect(onPrimaryAction).toHaveBeenCalledWith({ kind: "review", label: "开始今日复习" });
  });
});
