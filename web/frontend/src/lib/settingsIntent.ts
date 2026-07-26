/**
 * Heuristics for detecting "change my settings" style chat messages so the
 * UI can offer a settings-change confirmation instead of a normal answer.
 */

export const SETTINGS_PHRASES = [
  "回答短一点", "简短一点", "回答简洁", "少说一点", "回答详细", "讲深入", "更深入", "详细一点",
  "标准回答", "恢复标准", "正常详细", "引导我", "苏格拉底", "多提问", "直接讲解", "讲解式",
  "直接告诉我", "陪我练", "陪练", "多练习", "反馈直接", "直接批评", "严格一点", "反馈温和",
  "温和一点", "别太直接", "关闭记忆", "不要记忆", "停用记忆", "开启记忆", "打开记忆", "启用记忆",
];

export function looksLikeSettingsChange(message: string): boolean {
  const text = message.replace(/\s+/g, "").toLocaleLowerCase();
  return SETTINGS_PHRASES.some((phrase) => text.includes(phrase));
}
