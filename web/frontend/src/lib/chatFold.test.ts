import { describe, expect, it } from "vitest";

import {
  foldChatStream,
  initialChatStreamState,
  isStaleSeq,
  rememberSeq,
  streamEffects,
  type ChatStreamState,
} from "./chatFold";
import type { ChatStreamEvent } from "./api";
import type { ChatMessage } from "../types";

/**
 * W3 F1：把流式归约从 hook 里搬进**纯函数**（并让它对 `seq` 幂等）。
 *
 * 为什么值得搬：归约是流式正确性的根，但以前它埋在 hook 里、只能通过渲染间接测；
 * 而断线重连会把帧**重放**一次，重放必须被丢弃而不是把回答写两遍。
 */

function pending(): ChatStreamState {
  return foldChatStream(initialChatStreamState, {
    kind: "replace-messages",
    messages: [{ role: "assistant", content: "", pending: true } as ChatMessage],
  });
}

function frame(event: ChatStreamEvent["event"], data: Record<string, unknown>, meta: Record<string, unknown> = {}) {
  // 测试夹具：故意允许任意 payload，所以先过 unknown（union 收紧后不能再直接断言）。
  return { kind: "stream" as const, event: { event, data: { ...data, ...meta } } as unknown as ChatStreamEvent };
}

describe("foldChatStream：基本过渡", () => {
  it("delta 设置生成状态，缓冲刷新追加到末尾那条待完成消息", () => {
    const received = foldChatStream(pending(), frame("message_delta", { content: "你好" }));
    const state = foldChatStream(received, { kind: "delta-flush", content: "你好" });

    expect(state.messages[0].content).toBe("你好");
    expect(state.status).toBe("正在组织回答");
    expect(state.brandState).toBe("writing");
  });

  it("较早收到的正文刷新不覆盖后来的工具状态", () => {
    const received = foldChatStream(pending(), frame("message_delta", { content: "你好" }));
    const reading = foldChatStream(received, frame("status", {
      phase: "tool", message: "正在查找你的资料", tool_name: "rag_search",
    }));
    const flushed = foldChatStream(reading, { kind: "delta-flush", content: "你好" });

    expect(flushed.messages[0].content).toBe("你好");
    expect(flushed.status).toBe(reading.status);
    expect(flushed.brandState).toBe("reading");
  });

  it("narration 进过程，不进正文", () => {
    const state = foldChatStream(pending(), frame("message_delta", {
      content: "我先查一下资料。", call_role: "narration",
    }));

    expect(state.messages[0].content).toBe("");
    expect(state.messages[0].process?.at(-1)?.message).toBe("我先查一下资料。");
  });

  it("status 既更新状态行，也留一条过程", () => {
    const state = foldChatStream(pending(), frame("status", {
      phase: "tool", message: "正在查找你的资料", tool_name: "rag_search",
    }));

    expect(state.status).toBe("正在查找你的资料");
    expect(state.brandState).toBe("reading");
    expect(state.messages[0].process?.at(-1)?.toolName).toBe("rag_search");
  });

  it("citation / personalization 贴到消息上", () => {
    const cited = foldChatStream(pending(), frame("citation", {
      attribution: { kind: "local", sources: [] },
    }));
    const personalized = foldChatStream(cited, frame("personalization", { references: [{ id: "r1" }] }));

    expect(cited.messages[0].attribution).toEqual({ kind: "local", sources: [] });
    expect(cited.brandState).toBe("reading");
    expect(personalized.messages[0].personalization).toEqual([{ id: "r1" }]);
  });

  it("截断事件写进 truncated", () => {
    const state = foldChatStream(pending(), frame("answer_truncated", { continuing: false, continues: 2 }));

    expect(state.truncated).toEqual({ continuing: false });
    expect(state.status).toContain("截断");
  });

  it("run_completed 让品牌状态归位", () => {
    const state = foldChatStream(pending(), frame("run_completed", {
      chat_session_id: "s1", termination_reason: "final_answer",
    }));

    expect(state.brandState).toBe("ready");
  });

  it("settle 把最后一条标成已完成 / 失败 / 已停止", () => {
    const done = foldChatStream(pending(), { kind: "settle" });
    const failed = foldChatStream(pending(), { kind: "settle", failed: true });
    const stopped = foldChatStream(pending(), { kind: "settle", stopped: true });

    expect(done.messages[0].pending).toBe(false);
    expect(failed.messages[0].failed).toBe(true);
    expect(stopped.messages[0].stopped).toBe(true);
  });

  it("归约不处理的事件不改状态（连对象都不换，避免多余渲染）", () => {
    // 2026-10-17：practice / learning_update 已从事件表删除（死代码清理）；
    // 这里改用另一个「归约本身不改变状态」的事件（run_started 只由调用方处理副作用）。
    const before = pending();
    const after = foldChatStream(before, frame("run_started", { run_id: "r", chat_session_id: "s" }));

    expect(after).toBe(before);
  });
});

describe("seq 幂等（断线重连会重放）", () => {
  it("同一个 seq 再来一次算重放", () => {
    const event = frame("message_delta", { content: "x" }, { seq: 3, stream_id: "s1" }).event;

    expect(isStaleSeq({ s1: 3 }, event)).toBe(true);
    expect(isStaleSeq({ s1: 2 }, event)).toBe(false);
  });

  it("回退的 seq 算重放，更新的不算", () => {
    const stale = frame("message_delta", { content: "b" }, { seq: 2, stream_id: "s1" }).event;
    const fresh = frame("message_delta", { content: "c" }, { seq: 6, stream_id: "s1" }).event;

    expect(isStaleSeq({ s1: 5 }, stale)).toBe(true);
    expect(isStaleSeq({ s1: 5 }, fresh)).toBe(false);
  });

  it("换了 stream_id（新一轮）就互不影响", () => {
    const other = frame("message_delta", { content: "n" }, { seq: 1, stream_id: "s2" }).event;

    expect(isStaleSeq({ s1: 99 }, other)).toBe(false);
  });

  it("没有 seq 的帧不去重（老服务端/测试夹具）", () => {
    const event = frame("message_delta", { content: "x" }).event;

    expect(isStaleSeq({ s1: 9 }, event)).toBe(false);
    expect(rememberSeq({ s1: 9 }, event)).toEqual({ s1: 9 });
  });

  it("钩子用同一个进度表：记住了才判重放", () => {
    const event = frame("message_delta", { content: "x" }, { seq: 4, stream_id: "s1" }).event;
    const applied = rememberSeq({}, event);

    expect(applied).toEqual({ s1: 4 });
    expect(isStaleSeq(applied, event)).toBe(true);
  });

  it("重放帧一点都不改变状态（对象都不换）", () => {
    const event = frame("message_delta", { content: "x" }, { seq: 4, stream_id: "s1" }).event;
    const state = foldChatStream(pending(), { kind: "stream", event });
    const again = foldChatStream(state, { kind: "stream", event });

    expect(again).toBe(state);
  });

  it("正文由打字机缓冲追加（delta-flush），不受 seq 影响", () => {
    const once = foldChatStream(pending(), { kind: "delta-flush", content: "x" });
    const twice = foldChatStream(once, { kind: "delta-flush", content: "x" });

    expect(twice.messages[0].content).toBe("xx");
  });
});


describe("streamEffects：副作用要从纯函数里拿走", () => {
  it("run_started 带回会话 id", () => {
    const effects = streamEffects(frame("run_started", { run_id: "r", chat_session_id: "s9" }).event);

    expect(effects.sessionId).toBe("s9");
  });

  it("knowledge_context artifact 带回上下文", () => {
    const effects = streamEffects(frame("chat_artifact", {
      artifact: { type: "knowledge_context", artifact_id: "a1", context: { concepts: [] } },
    }).event);

    expect(effects.knowledgeContext).toEqual({ concepts: [] });
  });

  it("practice_ready 会被打上会话 id（靠传入的 sessionId，保持纯函数）", () => {
    const state = foldChatStream(pending(), {
      kind: "stream",
      sessionId: "s1",
      event: frame("chat_artifact", {
        artifact: { type: "practice_ready", artifact_id: "a2", question_ids: [1] },
      }).event,
    });

    expect((state.messages[0].artifacts?.[0] as { chat_session_id?: string }).chat_session_id).toBe("s1");
  });
});
