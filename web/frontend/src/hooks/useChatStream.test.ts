import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useChatStream, IGNORED_STREAM_EVENTS } from "./useChatStream";
import {
  CHAT_STREAM_EVENT_KINDS,
  type ChatStreamEventKind,
} from "../lib/chatStreamEvents";
import type { ChatStreamEvent, ChatStreamEventKindMatchesUnion } from "../lib/api";

/**
 * W3 F3：**漏订阅 = 静默丢帧**。
 *
 * 做法不是再写一张人工维护的清单（那种清单本身就会漂），而是：对**每一个**事件名喂一帧
 * 最小样本，断言它要么**真的改变了状态**，要么被明确列进 «IGNORED_STREAM_EVENTS» 并给出理由。
 * 新增事件名时，这条测试会立刻逼你二选一。
 *
 * 另有**类型级**对账：union 与运行时常量表必须互相覆盖（api.ts 的
 * «ChatStreamEventKindMatchesUnion»）；这里把它落成常量，让 tsc 真的去算它。
 */

const _typesReconciled: ChatStreamEventKindMatchesUnion = true;

const SAMPLES: Record<ChatStreamEventKind, ChatStreamEvent> = {
  run_started: { event: "run_started", data: { run_id: "r1", chat_session_id: "s1" } },
  message_delta: { event: "message_delta", data: { content: "片段", call_role: "finish" } },
  status: { event: "status", data: { phase: "tool", message: "正在查找资料" } },
  citation: { event: "citation", data: { attribution: { kind: "local", sources: [] } as never } },
  chat_artifact: {
    event: "chat_artifact",
    data: { artifact: {
      type: "practice_ready", artifact_id: "a1", chat_session_id: "s1", question_ids: [1],
    } as never },
  },
  personalization: { event: "personalization", data: { references: [] } },
  practice: { event: "practice", data: {} },
  learning_update: { event: "learning_update", data: {} },
  answer_truncated: { event: "answer_truncated", data: { continuing: false, continues: 2 } },
  run_completed: { event: "run_completed", data: { chat_session_id: "s1", termination_reason: "final_answer" } },
  run_failed: { event: "run_failed", data: { error: { code: "provider_error", message: "boom" } } },
};

function snapshot(hook: ReturnType<typeof useChatStream>) {
  return JSON.stringify({
    messages: hook.messages,
    status: hook.status,
    brandState: hook.brandState,
    truncated: hook.truncated,
  });
}

describe("chat stream event subscription", () => {
  it("对账常量本身是自洽的", () => {
    expect(_typesReconciled).toBe(true);
    // 每个事件名都要有样本，否则这条测试自己就漏了。
    expect(Object.keys(SAMPLES).sort()).toEqual([...CHAT_STREAM_EVENT_KINDS].sort());
  });

  it("每个事件要么改变状态，要么被明确忽略（并写明理由）", () => {
    const silentlyDropped: string[] = [];
    for (const kind of CHAT_STREAM_EVENT_KINDS) {
      const { result } = renderHook(() => useChatStream());
      act(() => result.current.setMessages([{ role: "assistant", content: "", pending: true }]));
      // 基线必须在"先把 settle 的效果落定"之后再取 —— 否则 settleLastMessage 自己造成的变化
      // 会让每个事件都显得"改变了状态"，这条测试就白测了（我第一版就是这么写的）。
      act(() => result.current.settleLastMessage());
      const before = snapshot(result.current);
      let threw = false;
      // run_started 这类事件的效果是**回调**（不是内部状态），所以也要把它算作"被处理"。
      const callbacks: string[] = [];
      act(() => {
        try {
          result.current.handleStreamEvent(SAMPLES[kind], {
            onRunStarted: () => callbacks.push("onRunStarted"),
          });
        } catch {
          // run_failed 是**故意**抛出的（由调用方转成错误界面）。
          threw = true;
        }
        result.current.settleLastMessage();
      });
      const changed = threw || callbacks.length > 0 || snapshot(result.current) !== before;
      if (!changed && !(kind in IGNORED_STREAM_EVENTS)) {
        silentlyDropped.push(kind);
      }
    }
    expect(silentlyDropped).toEqual([]);
  });

  it("被忽略的事件必须写明理由", () => {
    for (const reason of Object.values(IGNORED_STREAM_EVENTS)) {
      expect(String(reason).trim().length).toBeGreaterThan(8);
    }
  });
});


describe("W3 F1：断线重连重放不会把回答写两遍", () => {
  it("同一个 seq 的 delta 重放一次，正文只出现一次", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setMessages([{ role: "assistant", content: "", pending: true }]));

    const delta = {
      event: "message_delta" as const,
      data: { content: "只此一份", call_role: "finish" as const, seq: 7, stream_id: "s1" },
    };
    act(() => result.current.handleStreamEvent(delta));
    act(() => result.current.handleStreamEvent(delta)); // 重放
    act(() => result.current.settleLastMessage());

    expect(result.current.messages[0].content).toBe("只此一份");
  });

  it("序号更大的帧照常追加", () => {
    const { result } = renderHook(() => useChatStream());
    act(() => result.current.setMessages([{ role: "assistant", content: "", pending: true }]));

    act(() => result.current.handleStreamEvent({
      event: "message_delta", data: { content: "甲", call_role: "finish", seq: 1, stream_id: "s1" },
    }));
    act(() => result.current.handleStreamEvent({
      event: "message_delta", data: { content: "乙", call_role: "finish", seq: 2, stream_id: "s1" },
    }));
    act(() => result.current.settleLastMessage());

    expect(result.current.messages[0].content).toBe("甲乙");
  });

  it("store 只通过 applyEvent 这一个入口改状态", () => {
    const { result } = renderHook(() => useChatStream());

    expect(typeof result.current.applyEvent).toBe("function");
    act(() => result.current.applyEvent({
      event: "status", data: { phase: "tool", message: "正在查找你的资料", tool_name: "rag_search" },
    }));

    expect(result.current.status).toBe("正在查找你的资料");
    expect(result.current.brandState).toBe("reading");
  });
});

describe("缓冲正文的收尾", () => {
  it.each([
    { label: "停止", failed: false, stopped: true },
    { label: "失败", failed: true, stopped: false },
  ])("$label 后排空缓冲不会重新显示生成状态", ({ failed, stopped }) => {
    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.setMessages([{ role: "assistant", content: "", pending: true }]);
      result.current.applyEvent({ event: "message_delta", data: { content: "尚未刷新的正文" } });
      if (failed) expect(() => result.current.applyEvent(SAMPLES.run_failed)).toThrow("boom");
      // 与 ChatPage 的停止 / 失败分支保持相同顺序。
      result.current.setStatus("");
      result.current.settleLastMessage(failed, stopped);
    });

    expect(result.current.messages[0]).toMatchObject({
      content: "尚未刷新的正文", pending: false,
      ...(failed ? { failed: true } : { stopped: true }),
    });
    expect(result.current.status).toBe("");
  });
});
