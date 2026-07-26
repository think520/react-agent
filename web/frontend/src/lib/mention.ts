/**
 * Parsing for @mention triggers in the chat composer.
 */

const MENTION_PATTERN = /(?:^|\s)@([^\s@]*)$/;

export interface MentionMatch {
  /** The raw text after "@" (may be empty while the palette is open). */
  raw: string;
  /** Lowercased filter query; empty when a tab keyword ("资料"/"会话") is typed. */
  query: string;
  /** Tab forced by typing the keyword after "@", if any. */
  forcedTab: "document" | "session" | null;
}

export function parseMentionDraft(draft: string): MentionMatch | null {
  if (draft.startsWith("/")) return null;
  const match = draft.match(MENTION_PATTERN);
  if (!match) return null;
  const raw = match[1];
  const forcedTab = raw === "会话" ? "session" : raw === "资料" ? "document" : null;
  return { raw, query: forcedTab ? "" : raw.toLocaleLowerCase(), forcedTab };
}
