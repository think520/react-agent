import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import type { QuestionPipelineEvent } from "../lib/api";
import { useQuestionPipeline } from "./useQuestionPipeline";

/**
 * W1 E5 第二批："每题就绪即渲染"的前端一半 —— 管线事件到了就累积到界面状态里，
 * 而不是等整批出完。
 */

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, streamQuestionPipeline: vi.fn() } };
});

let emit: ((event: QuestionPipelineEvent) => void) | null = null;
let finish: (() => void) | null = null;

beforeEach(() => {
  emit = null;
  finish = null;
  // 真正的 SSE 连接会一直挂着，直到服务端收尾 —— mock 也要这样，
  // 否则"流已经结束"会把状态提前推成 done，测不出"边出边显示"。
  vi.mocked(api.streamQuestionPipeline).mockImplementation((
    _body: { topic: string; count?: number; document_ids?: string[] },
    onEvent: (event: QuestionPipelineEvent) => void,
  ) => {
    emit = onEvent;
    return new Promise<void>((resolve) => { finish = resolve; });
  });
});

afterEach(() => vi.clearAllMocks());

it("逐题累积：每收到一帧就多一道题，不等整批结束", async () => {
  const { result } = renderHook(() => useQuestionPipeline());

  await act(async () => { void result.current.start("极限", 3); });
  expect(result.current.status).toBe("running");

  await act(async () => { emit?.({ event: "pipeline_started", topic: "极限", count: 3 } as never); });
  await act(async () => { emit?.({ event: "quiz_plan", source: "fallback", plan: [{ topic: "极限" }] } as never); });
  expect(result.current.plan).toHaveLength(1);

  await act(async () => {
    emit?.({ event: "quiz_question_emitted", index: 0, total: 3, question_id: 11, question: { id: 11, question: "第一题" } } as never);
  });
  expect(result.current.questionIds).toEqual([11]);
  expect(result.current.status).toBe("running");

  await act(async () => {
    emit?.({ event: "quiz_question_emitted", index: 1, total: 3, question_id: 12, question: { id: 12, question: "第二题" } } as never);
  });
  expect(result.current.questions.map((item) => item.question)).toEqual(["第一题", "第二题"]);

  await act(async () => { emit?.({ event: "pipeline_done", question_ids: [11, 12], total: 3 } as never); });
  await act(async () => { finish?.(); });
  await waitFor(() => expect(result.current.status).toBe("done"));
  expect(result.current.questionIds).toEqual([11, 12]);
});

it("没有证据时如实失败，而不是当作「出好了 0 道题」", async () => {
  const { result } = renderHook(() => useQuestionPipeline());

  await act(async () => { void result.current.start("不存在的主题", 3); });
  await act(async () => {
    emit?.({ event: "pipeline_failed", code: "no_evidence", error: "没有找到可用于出题的资料。" } as never);
  });

  await waitFor(() => expect(result.current.status).toBe("failed"));
  expect(result.current.error).toContain("没有找到");
  expect(result.current.questions).toEqual([]);
});

it("取消后保留已就绪的题", async () => {
  const { result } = renderHook(() => useQuestionPipeline());

  await act(async () => { void result.current.start("极限", 3); });
  await act(async () => {
    emit?.({ event: "quiz_question_emitted", index: 0, total: 3, question_id: 11, question: { id: 11, question: "第一题" } } as never);
  });
  await act(async () => { emit?.({ event: "pipeline_cancelled", emitted: 1, total: 3 } as never); });

  await waitFor(() => expect(result.current.status).toBe("cancelled"));
  expect(result.current.questionIds).toEqual([11]);
});
