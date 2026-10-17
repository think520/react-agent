/**
 * W3 F3：SSE 事件名的**唯一运行时来源**。
 *
 * 以前事件名只在 `ChatStreamEvent` 这个**类型** union 里出现过 —— 类型在运行时不存在，所以
 * 没人能枚举它，也没人能在「后端新增一个事件、前端忘了订阅」时报警：那一帧会被**静默丢掉**。
 * 现在把名字固化成运行时常量，并让类型与它互相牵引（见 api.ts 的对账类型与
 * hooks 的逐事件行为测试）。
 */

export const CHAT_STREAM_EVENT_KINDS = [
  "run_started",
  "message_delta",
  "status",
  "citation",
  "chat_artifact",
  "personalization",
  "answer_truncated",
  "run_completed",
  "run_failed",
] as const;

export type ChatStreamEventKind = (typeof CHAT_STREAM_EVENT_KINDS)[number];

/** 运行期判断：这个字符串是不是我们认得的事件名（坏帧/新事件都能据此识别）。 */
export function isChatStreamEventKind(value: unknown): value is ChatStreamEventKind {
  return typeof value === "string" && (CHAT_STREAM_EVENT_KINDS as readonly string[]).includes(value);
}