import type { ActivePracticeSummary, DataLoadStatus, DocumentSummary, ReviewQueue } from "../types";
import { readExperienceProgress } from "./experienceLesson";

export type WelcomePrimaryAction =
  | { kind: "resume-practice"; label: string; practiceSessionId: number }
  | { kind: "review"; label: string }
  | { kind: "retry"; label: string }
  | { kind: "loading"; label: string }
  | { kind: "library"; label: string }
  | { kind: "experience"; label: string }
  | { kind: "import"; label: string };

export function selectWelcomePrimaryAction({
  review,
  reviewStatus,
  activePractices,
  activePracticeStatus,
  documents,
  documentsUnavailable = false,
}: {
  review: ReviewQueue | null;
  reviewStatus: DataLoadStatus;
  activePractices: ActivePracticeSummary[];
  activePracticeStatus: DataLoadStatus;
  documents: DocumentSummary[];
  documentsUnavailable?: boolean;
}): WelcomePrimaryAction {
  if (activePracticeStatus === "ready" && activePractices.length) {
    return { kind: "resume-practice", label: "继续上次练习", practiceSessionId: activePractices[0].practice_session_id };
  }
  if (reviewStatus === "ready" && (review?.due_concepts.length || 0) > 0) {
    return { kind: "review", label: "开始今日复习" };
  }
  if (reviewStatus === "ready" && ((review?.wrong_total ?? review?.wrong_answers.length ?? 0) > 0)) {
    return { kind: "review", label: "回顾错题" };
  }
  if (reviewStatus === "ready" && (review?.weaknesses.length || 0) > 0) {
    return { kind: "review", label: "补强薄弱点" };
  }
  if (documentsUnavailable || reviewStatus === "error" || activePracticeStatus === "error") {
    return { kind: "retry", label: "重试读取学习状态" };
  }
  if (reviewStatus === "loading" || activePracticeStatus === "loading") {
    return { kind: "loading", label: "正在读取学习状态…" };
  }
  if (documents.length) return { kind: "library", label: "打开资料库继续" };
  if (!readExperienceProgress().completed) {
    return { kind: "experience", label: readExperienceProgress().answer ? "继续体验课" : "体验一节课" };
  }
  return { kind: "import", label: "导入第一份资料" };
}
