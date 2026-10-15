/**
 * W1 E5：实时练习卡片的显示标签。
 *
 * 原则：认识的取值翻成中文，**不认识的如实显示原值** —— 编一个中文标签会让用户
 * 以为系统认识这个类型（数据里真出现新类型时，我们宁可显示得难看一点）。
 */

const TYPE_LABELS: Record<string, string> = {
  single_choice: "单选题",
  multiple_choice: "多选题",
  short_answer: "简答题",
  true_false: "判断题",
};

// 练习页的历史文案带"难度"二字，这里给短标签，页面自己决定怎么拼。
const DIFFICULTY_LABELS: Record<string, string> = {
  easy: "简单",
  medium: "中等",
  hard: "较难",
};

export function questionTypeLabel(type?: string | null): string {
  const value = (type || "").trim();
  return TYPE_LABELS[value] || value;
}

export function difficultyLabel(difficulty?: string | null): string {
  const value = (difficulty || "").trim();
  return DIFFICULTY_LABELS[value] || value;
}
