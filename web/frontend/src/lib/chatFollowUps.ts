import type { ChatMessage } from "../types";

export interface FollowUpSuggestion {
  label: string;
  prompt: string;
}

const DENSE_PATTERN = /```|\$\$|\\\(|^#{1,3}\s/m;

/** Build 3 concise, study-oriented follow-up prompts for a completed assistant reply. */
export function buildFollowUpSuggestions(message: ChatMessage): FollowUpSuggestion[] {
  if (
    message.role !== "assistant"
    || message.pending
    || message.failed
    || message.stopped
    || !message.content.trim()
  ) {
    return [];
  }

  const isDense = message.content.length > 260 || DENSE_PATTERN.test(message.content);
  const isGrounded = message.attribution?.kind === "local" || message.attribution?.kind === "mixed";

  if (isDense && isGrounded) {
    return [
      { label: "换个直觉类比", prompt: "请用更贴近直觉的生活类比，再通俗讲一遍核心思路。" },
      { label: "列出易混淆点", prompt: "这部分内容有哪些最容易理解偏差或混淆的地方？请逐条对比。" },
      { label: "对照资料补全推导", prompt: "请结合刚才引用的资料原文，把关键前提条件和完整推导补全。" },
    ];
  }
  if (isDense) {
    return [
      { label: "换个直觉类比", prompt: "请用更贴近直觉的生活类比，再通俗讲一遍核心思路。" },
      { label: "列出易混淆点", prompt: "这部分内容有哪些最容易理解偏差或混淆的地方？请逐条对比。" },
      { label: "出 2 道小题考我", prompt: "请围绕你刚才讲的核心概念出 2 道小测验题，先别给答案，等我作答。" },
    ];
  }
  if (isGrounded) {
    return [
      { label: "展开讲关键细节", prompt: "请进一步展开上面最关键的细节和适用边界。" },
      { label: "举一个具体例子", prompt: "能结合具体例子完整走一遍刚才说的方法或步骤吗？" },
      { label: "对照资料梳理脉络", prompt: "请把这段内容放到我导入的资料脉络里，梳理它与前后知识点的联系。" },
    ];
  }
  return [
    { label: "展开讲关键细节", prompt: "请进一步展开上面最关键的细节和适用边界。" },
    { label: "举一个具体例子", prompt: "能结合具体例子完整走一遍刚才说的方法或步骤吗？" },
    { label: "出 2 道小题考我", prompt: "请围绕你刚才讲的核心概念出 2 道小测验题，先别给答案，等我作答。" },
  ];
}
