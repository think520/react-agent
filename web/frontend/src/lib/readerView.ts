/**
 * 阅读器视图的决策规则（共识 Q1/Q2/Q5/Q6/Q7）。
 *
 * 抽成纯函数的理由很实际：这段规则的每一次分叉（默认原文、哪些格式能页内渲染、
 * 跳转时强制分段、没有原件时不给切换）以前散在组件里，只有真实浏览器才能验证；
 * 现在它可以在 CI 里被逐条断言，而 Playwright 的 live 检查负责验证渲染本身。
 */

export type ReaderView = "original" | "sections";
export type InlineOriginalKind = "markdown" | "pdf" | null;

export const READER_VIEW_KEY = "bobodan:reader-view";
/** 浏览器能当文本渲染的格式：走我们自己的排版。 */
const MARKDOWN_EXTENSIONS = new Set(["md", "markdown", "txt"]);

export function documentExtension(source: string | undefined): string {
  const name = (source || "").toLowerCase();
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1) : "";
}

/** 页内能渲染成什么：markdown 用我们的排版，pdf 交给浏览器内置阅读器，其余为 null。 */
export function inlineOriginalKind(source: string | undefined): InlineOriginalKind {
  const extension = documentExtension(source);
  if (MARKDOWN_EXTENSIONS.has(extension)) return "markdown";
  if (extension === "pdf") return "pdf";
  return null;
}

export interface ReaderViewInput {
  /** 后端判定：这份资料有没有原件（Q5：按"有没有"而不是按类型白名单）。 */
  hasOriginal: boolean;
  source: string | undefined;
  /** 用户记住的偏好。 */
  preference: ReaderView;
  /** 本次是否由跳转（搜索/引用）强制分段。 */
  forcedSections: boolean;
}

export interface ReaderViewDecision {
  /** 本次实际使用的视图。 */
  view: ReaderView;
  /** 是否显示「原文 | 按小节」切换（不能页内显示原件时隐藏，避免假按钮）。 */
  showSwitch: boolean;
  /** 页内原文用哪个渲染器。 */
  inlineKind: InlineOriginalKind;
  /** 非页内可渲染但有原件时，是否给「用系统打开」。 */
  offerSystemOpen: boolean;
}

export function resolveReaderView(input: ReaderViewInput): ReaderViewDecision {
  const inlineKind = input.hasOriginal ? inlineOriginalKind(input.source) : null;
  const showSwitch = inlineKind !== null;
  const view: ReaderView = input.forcedSections || !showSwitch ? "sections" : input.preference;
  return {
    view,
    showSwitch,
    inlineKind,
    offerSystemOpen: Boolean(input.hasOriginal) && inlineKind === null,
  };
}
