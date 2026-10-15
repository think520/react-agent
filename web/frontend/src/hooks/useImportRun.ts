import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import type { ImportBatchResult } from "../lib/api";

/** 轮询间隔：够快让进度看起来是活的，又不至于把后端问爆。 */
const DEFAULT_POLL_MS = 400;

export interface ImportRunProgress {
  phase: string;
  filesDone: number;
  filesTotal: number;
  sourcesDone: number;
  sourcesTotal: number;
  current: string;
}

interface ImportPayload {
  imported: string[];
  duplicates?: Array<{ filename: string; existing: string; reason: string }>;
  rejected: unknown[];
  pending?: unknown[];
  cancelled?: boolean;
  results?: ImportBatchResult[];
  library_sync: { extraction_counts?: Record<string, number>; error_files?: number };
}

/**
 * E8 收尾：把导入跑成**可观察、可取消**的运行。
 *
 * 后端已经有 «POST /api/kb/imports» + «GET /api/kb/imports/{id}» + «POST …/cancel»；
 * 这个 hook 负责轮询进度、在终态把本次批次结果交回来，并在用户点取消时调取消端点。
 * 取消是**协作式**的（文件边界生效）：返回的结果里 «cancelled=true»，已经收下的仍在。
 */
export function useImportRun(pollMs: number = DEFAULT_POLL_MS) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<ImportRunProgress | null>(null);
  const [error, setError] = useState("");
  const runIdRef = useRef<string | null>(null);
  const disposedRef = useRef(false);

  useEffect(() => () => { disposedRef.current = true; }, []);

  const start = useCallback(async (
    files: File[],
    duplicateStrategy: "keep_existing" | "save_copy" = "keep_existing",
  ): Promise<ImportPayload | null> => {
    setError("");
    setRunning(true);
    setProgress({
      phase: "receiving", filesDone: 0, filesTotal: files.length,
      sourcesDone: 0, sourcesTotal: 0, current: "",
    });
    try {
      const { import_id } = await api.startImport(files, duplicateStrategy);
      runIdRef.current = import_id;
      for (;;) {
        const snapshot = await api.importStatus(import_id);
        if (disposedRef.current) return null;
        setProgress({
          phase: snapshot.phase,
          filesDone: snapshot.files_done,
          filesTotal: snapshot.files_total,
          sourcesDone: snapshot.sources_done,
          sourcesTotal: snapshot.sources_total,
          current: snapshot.current,
        });
        if (snapshot.status !== "running") {
          setRunning(false);
          setProgress(null);
          if (snapshot.status === "failed") {
            const message = snapshot.error || "导入失败。";
            setError(message);
            // 抛出去，让调用方用自己那套错误呈现（这里同时留一份状态给进度条用）。
            throw new Error(message);
          }
          return (snapshot.result as ImportPayload | null) ?? null;
        }
        await new Promise((resolve) => window.setTimeout(resolve, pollMs));
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "导入失败。";
      if (!disposedRef.current) {
        setError(message);
        setRunning(false);
        setProgress(null);
      }
      // 既留一份状态给进度条，也抛给调用方用自己那套错误呈现（AppShell 的 catch）。
      throw reason instanceof Error ? reason : new Error(message);
    } finally {
      runIdRef.current = null;
    }
  }, [pollMs]);

  const cancel = useCallback(async () => {
    const importId = runIdRef.current;
    if (!importId) return;
    try {
      await api.cancelImport(importId);
    } catch {
      // 取消失败不额外打扰用户：下一轮轮询会看到真实状态（服务端只在文件边界停）。
    }
  }, []);

  return { start, cancel, running, progress, error };
}
