import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { LearningContext } from "./LearningContext";

describe("LearningContext review status", () => {
  it("does not report an empty queue when reading the queue failed", () => {
    render(<MemoryRouter><LearningContext
      documents={[]}
      review={null}
      reviewStatus="error"
      selectedDocumentIds={[]}
      toggleDocumentScope={vi.fn()}
      knowledgeContext={null}
      sourceContext={null}
      onOpenConcept={vi.fn()}
      onOpenMap={vi.fn()}
    /></MemoryRouter>);

    fireEvent.click(screen.getByRole("tab", { name: "学习" }));

    expect(screen.getByText("暂时无法读取复习状态")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
    expect(screen.queryByText("今天没有到期内容，可以开始一轮新练习。")).toBeNull();
  });
});
