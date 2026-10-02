/**
 * E3: the wrong-answer variant endpoint degrades safely instead of failing —
 * chunk evidence -> same-concept question -> replay the original. The user must
 * still learn which path was taken, so the mode maps to a visible reason.
 *
 * W1 E3 起后端还会给一个更精确的 «reason»：**证据缺失**与**生成失败**是两件事，
 * 未配置模型又是第三件（旧文案把它们都说成"原题证据已失效"）。
 */
export function wrongAnswerFallbackNotice(mode?: string, reason?: string): string | null {
  if (reason === "no_provider") return "AI 模型未配置，本轮先重练原题（在设置里配置后即可生成变式）。";
  if (reason === "generation_failed") return "这次没能生成变式题，本轮先重练原题。";
  if (reason === "variant_failed") return "变式生成失败，已按同一概念重新出题。";
  if (reason === "evidence_missing") return "原题证据已失效，已按同一概念重新出题。";
  if (reason === "no_evidence") return "这道题没有可用的原文证据，本轮先重练原题。";
  // 老后端没有 reason 时退回按 mode 判断（保持兼容）。
  if (mode === "concept_fallback") return "原题证据已失效，已按同一概念重新出题。";
  if (mode === "replay") return "暂时无法生成变式题，本轮先重练原题。";
  return null;
}
