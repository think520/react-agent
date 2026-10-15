/**
 * W1 E7：笔记里的**托管区块**（自定语法）。
 *
 * 三家参考项目都没有等价机制，规则由我们定。最重要的一条：
 * **只重写标记之间的内容，永不碰用户手写的东西**。
 *
 * 语法：
 *   <!-- bobodan:managed:highlights:doc-1 start -->
 *   …生成的内容…
 *   <!-- bobodan:managed:highlights:doc-1 end -->
 *
 * 结束标记带 key：这样"两个资料的划线块放在同一篇笔记里"不会互相吞掉；
 * 而**没有结束标记**（用户手抖删了）时，我们把残留的起始标记当作普通文本 ——
 * 绝不能把后面的手写内容一起当成托管区。
 */

export const MANAGED_START = (key: string) => `<!-- bobodan:managed:${key} start -->`;
export const MANAGED_END = (key: string) => `<!-- bobodan:managed:${key} end -->`;

export interface ManagedResult {
  text: string;
  changed: boolean;
}

export interface HighlightLike {
  quote: string;
  resolution?: { status?: string; chunk_id?: string | null };
}

const STATUS_NOTE: Record<string, string> = {
  relocated: "（位置已更新）",
  stale: "（已失效，需要在原文里重新指认）",
};

/** 把划线渲染成托管区块的正文：顺序稳定（按引文排序），同一批输入永远一样。 */
export function renderHighlightsBlock(anchors: HighlightLike[]): string {
  if (!anchors.length) {
    return "（这篇资料还没有划线。）";
  }
  return [...anchors]
    .sort((left, right) => left.quote.localeCompare(right.quote, "zh-Hans-CN"))
    .map((anchor) => `- 「${anchor.quote}」${STATUS_NOTE[anchor.resolution?.status || ""] || ""}`)
    .join("\n");
}

/** 读出某个 key 的托管区块正文；没有就返回 null。 */
export function readManagedBlock(text: string, key: string): string | null {
  const start = text.indexOf(MANAGED_START(key));
  if (start < 0) return null;
  const end = text.indexOf(MANAGED_END(key), start);
  if (end < 0) return null;
  return text.slice(start + MANAGED_START(key).length, end);
}

/**
 * 写入/更新托管区块：
 * - 已有该 key 的完整区块 → 只替换中间；
 * - 同一份内容 → 原样返回（changed=false，便于"没变就不写"）；
 * - 否则追加到末尾（保留用户已有内容）。
 */
export function upsertManagedBlock(text: string, key: string, body: string): ManagedResult {
  const block = `${MANAGED_START(key)}\n${body}\n${MANAGED_END(key)}`;
  const start = text.indexOf(MANAGED_START(key));
  const end = start >= 0 ? text.indexOf(MANAGED_END(key), start) : -1;

  if (start >= 0 && end >= 0) {
    const replaced = text.slice(0, start) + block + text.slice(end + MANAGED_END(key).length);
    return { text: replaced, changed: replaced !== text };
  }

  const separator = text.trim().length ? (text.endsWith("\n") ? "\n" : "\n\n") : "";
  const appended = `${text}${separator}${block}\n`;
  return { text: appended, changed: appended !== text };
}
