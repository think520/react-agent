/**
 * E3: the wrong-answer variant endpoint degrades safely instead of failing —
 * chunk evidence -> same-concept question -> replay the original. The user must
 * still learn which path was taken, so the mode maps to a visible reason.
 */
export function wrongAnswerFallbackNotice(mode?: string): string | null {
  if (mode === "concept_fallback") return "原题证据已失效，已按同一概念重新出题。";
  if (mode === "replay") return "暂时无法生成变式题，本轮先重练原题。";
  return null;
}
