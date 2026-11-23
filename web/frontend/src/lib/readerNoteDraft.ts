export const MAX_NOTE_CONTENT_LENGTH = 5000;

export interface HighlightNoteInput {
  quote: string;
  chunk_id?: string | null;
  heading?: string | null;
}

export interface NoteDocumentReference {
  document_id: string;
  chunk_id?: string;
  title: string;
  page?: number;
}

function clampNoteContent(content: string): { content: string; truncated: boolean } {
  const trimmed = content.trim();
  if (trimmed.length <= MAX_NOTE_CONTENT_LENGTH) {
    return { content: trimmed, truncated: false };
  }
  const suffix = "\n\n…（内容过长已截断）";
  const sliceLen = Math.max(0, MAX_NOTE_CONTENT_LENGTH - suffix.length);
  return { content: trimmed.slice(0, sliceLen).trimEnd() + suffix, truncated: true };
}

export function buildHighlightQuoteBlock(
  quote: string,
  docTitle: string,
  heading?: string | null,
): string {
  const lines = quote
    .trim()
    .split(/\r?\n/)
    .map((line) => `> ${line.trimEnd()}`);
  const location = heading?.trim() ? `《${docTitle}》 · ${heading.trim()}` : `《${docTitle}》`;
  lines.push(`—— 摘自 ${location}`);
  return lines.join("\n");
}

export function formatSingleHighlightNote(
  quote: string,
  docTitle: string,
  heading?: string | null,
): { title: string; content: string } {
  const safeTitle = (docTitle || "未命名资料").trim();
  const title = `摘录 · ${safeTitle}`.slice(0, 120);
  const block = buildHighlightQuoteBlock(quote, safeTitle, heading);
  return { title, content: clampNoteContent(block).content };
}

export function formatHighlightsSummaryNote(
  anchors: HighlightNoteInput[],
  docTitle: string,
): { title: string; content: string } {
  const safeTitle = (docTitle || "未命名资料").trim();
  const title = `划线汇总 · ${safeTitle}`.slice(0, 120);
  const body = anchors
    .filter((item) => item.quote.trim())
    .map((item) => {
      const quoted = item.quote
        .trim()
        .split(/\r?\n/)
        .map((line) => `> ${line.trimEnd()}`)
        .join("\n");
      return item.heading?.trim() ? `${quoted}\n—— 小节：${item.heading.trim()}` : quoted;
    })
    .join("\n\n");
  const full = `## 《${safeTitle}》划线摘录\n\n${body}`;
  return { title, content: clampNoteContent(full).content };
}

export function appendHighlightToNoteContent(
  existingContent: string,
  addition: string,
): { content: string; truncated: boolean } {
  const cleanExisting = existingContent.trimEnd();
  const cleanAddition = addition.trim();
  if (!cleanExisting) return clampNoteContent(cleanAddition);
  if (!cleanAddition) return clampNoteContent(cleanExisting);
  return clampNoteContent(`${cleanExisting}\n\n${cleanAddition}`);
}

export function mergeDocumentReferences(
  existing: NoteDocumentReference[] | undefined,
  additions: NoteDocumentReference[],
): NoteDocumentReference[] {
  const result: NoteDocumentReference[] = [];
  const seen = new Set<string>();
  for (const ref of [...(existing || []), ...additions]) {
    if (!ref.document_id) continue;
    const key = `${ref.document_id}:${ref.chunk_id || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(ref);
  }
  return result.slice(0, 50);
}
