import type { QuestionBank, QuestionBankState } from "../../types";

/** 题库页的常量与纯函数（2026-10-17 M6：从 QuestionBankPage 搬出，让页面回到 ≤600 行）。 */
export const PAGE_SIZE = 20;

export const FILTERS: Array<{ key: string; label: string }> = [
  { key: "all", label: "全部" },
  { key: "unanswered", label: "未作答" },
  { key: "incorrect", label: "错题" },
  { key: "partial", label: "基本正确" },
  { key: "correct", label: "答对" },
  { key: "bookmarked", label: "已收藏" },
];

// The state is the noun the bulk action operates on, so no verb has to be
// guessed per state ("重练" is only right for the wrong-answer bucket).
export const BULK_NOUNS: Record<string, string> = {
  unanswered: "未作答题",
  incorrect: "错题",
  partial: "基本正确题",
  correct: "答对题",
  bookmarked: "收藏题",
};

export const TYPE_OPTIONS = [
  { value: "", label: "全部题型" },
  { value: "single_choice", label: "单选题" },
  { value: "true_false", label: "判断题" },
  { value: "short_answer", label: "简答题" },
];

export const DIFFICULTY_OPTIONS = [
  { value: "", label: "全部难度" },
  { value: "easy", label: "简单" },
  { value: "medium", label: "中等" },
  { value: "hard", label: "较难" },
];

/** A material is stored as a full path; the tail is what identifies it in a menu. */
export function materialLabel(source: string) {
  const tail = source.split(/[\\/]/).pop() || source;
  const name = tail.replace(/\.[^.]+$/, "");
  return name.length > 26 ? name.slice(0, 25) + "…" : name;
}

export const STATE_LABELS: Record<QuestionBankState, string> = {
  unanswered: "未作答",
  correct: "答对",
  partial: "基本正确",
  incorrect: "答错",
};

export function stateLabel(state: QuestionBankState) {
  return STATE_LABELS[state] || state;
}

export function filterCount(overview: QuestionBank["overview"], key: string) {
  if (key === "all") return overview.total;
  if (key === "bookmarked") return overview.bookmarked;
  if (key === "unanswered") return overview.unanswered;
  if (key === "correct") return overview.correct;
  if (key === "partial") return overview.partial;
  if (key === "incorrect") return overview.incorrect;
  return 0;
}

/** D7: a local-first product must let the user take their data out and put it back. */
export function todayStamp() {
  return new Date().toISOString().slice(0, 10);
}

export function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
