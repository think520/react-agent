import { beforeEach, describe, expect, it } from "vitest";

import type { ReviewQueue } from "../types";
import { writeExperienceProgress } from "./experienceLesson";
import { selectWelcomePrimaryAction } from "./welcomeAction";

const emptyQueue: ReviewQueue = { due_concepts: [], wrong_answers: [], weaknesses: [] };
const ready = { reviewStatus: "ready" as const, activePracticeStatus: "ready" as const, review: emptyQueue, activePractices: [], documents: [] };

beforeEach(() => window.localStorage.clear());

describe("Chat welcome primary action", () => {
  it("resumes active work before suggesting a new task", () => {
    const action = selectWelcomePrimaryAction({
      ...ready,
      review: { ...emptyQueue, due_concepts: [{}] },
      activePractices: [{ practice_session_id: 27, updated_at: "", question_count: 3 }],
    });
    expect(action).toEqual({ kind: "resume-practice", label: "继续上次练习", practiceSessionId: 27 });
  });

  it("prioritizes due review, and does not treat a failed read as an empty queue", () => {
    expect(selectWelcomePrimaryAction({ ...ready, review: { ...emptyQueue, due_concepts: [{}] } }).kind).toBe("review");
    expect(selectWelcomePrimaryAction({ ...ready, reviewStatus: "error", review: null }).kind).toBe("retry");
  });

  it("offers the sample lesson first, then a real library action when materials exist", () => {
    expect(selectWelcomePrimaryAction(ready)).toEqual({ kind: "experience", label: "体验一节课" });
    expect(selectWelcomePrimaryAction({ ...ready, documents: [{ document_id: "doc-1" } as never] }).kind).toBe("library");
  });

  it("resumes saved sample progress and stops promoting a completed sample", () => {
    writeExperienceProgress({ answer: "B", completed: false });
    expect(selectWelcomePrimaryAction(ready).label).toBe("继续体验课");
    writeExperienceProgress({ answer: "B", completed: true });
    expect(selectWelcomePrimaryAction(ready)).toEqual({ kind: "import", label: "导入第一份资料" });
  });
});
