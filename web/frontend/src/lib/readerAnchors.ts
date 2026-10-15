/**
 * W1 E7 第二批：把阅读器里的选区变成**锚点**（四元组 + 引文）。
 *
 * 关键取舍：DOM 里的文字是**渲染后**的（markdown 的 `**`、`#` 都不见了），
 * 而分段文本是原文 —— 偏移只有在原文里真的找得到才算数；找不到就如实存 null，
 * 不编一个一存进去就会在重锚定时失效的偏移。
 */

export interface AnchorSection {
  chunk_id: string;
  text: string;
}

export interface AnchorDraft {
  chunk_id: string;
  quote: string;
  char_start: number | null;
  char_end: number | null;
}

const MAX_QUOTE = 1200;

function collapse(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/** 在**原文**里找引文的位置；找不到返回 null（不猜）。 */
export function resolveQuoteOffsets(
  sectionText: string,
  quote: string,
): { char_start: number; char_end: number } | null {
  const needle = collapse(quote);
  if (!needle) return null;

  const exact = sectionText.indexOf(quote.trim());
  if (exact >= 0) {
    return { char_start: exact, char_end: exact + quote.trim().length };
  }

  // 渲染会把连续空白压成一个空格：把两边都压过之后再找，
  // 命中时按"压缩后的比例"不成立，所以只在长度一致时采用。
  const collapsedText = collapse(sectionText);
  const found = collapsedText.indexOf(needle);
  if (found >= 0 && collapsedText.length === sectionText.length) {
    return { char_start: found, char_end: found + needle.length };
  }
  if (found >= 0) {
    // 文本长度变了（说明确实有空白差异）：偏移不可靠，如实返回 null。
    return null;
  }
  return null;
}

/** 从 DOM 选区得到锚点草稿：chunk_id 取最近的分段，引文取选区文字。 */
export function anchorDraftFromRange(
  range: Range | null,
  sections: AnchorSection[],
): AnchorDraft | null {
  if (!range) return null;
  const quote = collapse(range.toString()).slice(0, MAX_QUOTE);
  if (!quote) return null;

  const start = range.startContainer;
  const element = (start.nodeType === Node.ELEMENT_NODE ? (start as Element) : start.parentElement);
  const section = element?.closest?.("[data-chunk-id]") as HTMLElement | null;
  const chunkId = section?.dataset?.chunkId || "";
  if (!chunkId) return null;

  const raw = sections.find((item) => item.chunk_id === chunkId)?.text ?? "";
  const offsets = resolveQuoteOffsets(raw, quote);
  return {
    chunk_id: chunkId,
    quote,
    char_start: offsets ? offsets.char_start : null,
    char_end: offsets ? offsets.char_end : null,
  };
}
