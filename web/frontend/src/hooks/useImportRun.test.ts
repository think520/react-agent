import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { useImportRun } from "./useImportRun";

/**
 * E8 收尾：界面要能看见**运行中的进度**并**取消**。
 * 服务层与 HTTP 端点已就绪（POST /api/kb/imports + GET 轮询 + POST cancel），
 * 这里钉住前端的运行态控制。
 */

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, startImport: vi.fn(), importStatus: vi.fn(), cancelImport: vi.fn() },
  };
});

const file = new File(["# a"], "a.md", { type: "text/markdown" });

function snapshot(overrides: Record<string, unknown> = {}) {
  return {
    import_id: "run-1", status: "running", phase: "indexing",
    files_total: 1, files_done: 1, current: "a.md",
    sources_total: 9, sources_done: 0, error: "", result: null,
    ...overrides,
  } as never;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(api.startImport).mockResolvedValue({ ok: true, import_id: "run-1" } as never);
  vi.mocked(api.cancelImport).mockResolvedValue({ ok: true, cancelled: true } as never);
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

it("轮询进度，到终态把结果交回来并收起进度", async () => {
  const payload = { imported: ["a.md"], rejected: [], results: [{ filename: "a.md", status: "imported", searchable: true }], library_sync: { extraction_counts: { complete: 1 } } };
  vi.mocked(api.importStatus)
    .mockResolvedValueOnce(snapshot({ sources_done: 3 }))
    .mockResolvedValueOnce(snapshot({ status: "completed", sources_done: 9, result: payload }));

  const { result } = renderHook(() => useImportRun(100));
  let started!: Promise<unknown>;
  await act(async () => { started = result.current.start([file]); });

  expect(result.current.running).toBe(true);
  expect(result.current.progress?.sourcesDone).toBe(3);

  await act(async () => { await vi.advanceTimersByTimeAsync(150); });
  expect(await started).toEqual(payload);
  expect(result.current.running).toBe(false);
  expect(result.current.progress).toBeNull();
  expect(result.current.error).toBe("");
});

it("取消时调用取消端点（用当前 run 的 id）", async () => {
  vi.mocked(api.importStatus).mockResolvedValue(snapshot({ sources_done: 1 }));

  const { result } = renderHook(() => useImportRun(100));
  let started!: Promise<unknown>;
  await act(async () => { started = result.current.start([file]); });

  await act(async () => { await result.current.cancel(); });
  expect(api.cancelImport).toHaveBeenCalledWith("run-1");

  // 收尾，避免悬挂的轮询
  vi.mocked(api.importStatus).mockResolvedValue(snapshot({ status: "cancelled" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(150); });
  await started;
});

it("失败时把原因说出来，不装作成功", async () => {
  vi.mocked(api.importStatus).mockResolvedValue(snapshot({ status: "failed", error: "磁盘满了" }));

  const { result } = renderHook(() => useImportRun(100));
  let started!: Promise<unknown>;
  // 立刻挂上 handler：失败是**预期**的，不能让 vitest 报"未处理的拒绝"。
  await act(async () => { started = result.current.start([file]).catch((error) => error); });

  expect((await started) as Error).toMatchObject({ message: "磁盘满了" });
  expect(result.current.running).toBe(false);
  expect(result.current.error).toBe("磁盘满了");
});
