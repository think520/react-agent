import { type ChangeEvent, useCallback, useEffect, useRef, useState } from "react";

import { useImportRun } from "./useImportRun";
import { errorCodeOf } from "../lib/errorHints";
import { toErrorMessage } from "../lib/errors";
import { clearImportReport, emptyDocumentImport, type DocumentImportState } from "../lib/importState";
import { describeDocumentImport } from "../lib/importSummary";
import type { LibrarySummary } from "../types";

interface Options {
  /** 当前资料库；没有资料库时导入先引导新建，并记住拖进来的文件。 */
  activeLibrary: LibrarySummary | null;
  /** 引导新建资料库（带着待导入的文件数）。 */
  openLibrarySetup: (options: { initialMode: "create"; importCount: number }) => void;
  /** 导入结束后刷新外壳数据（资料列表、复习队列…）。 */
  reloadScopedData: () => Promise<unknown>;
  /** 导入结束后去资料库看结果。 */
  onFinished: () => void;
}

/**
 * 资料导入的全部状态与动作（2026-11-11 从 AppShell 原样拆出，行为不变）：
 * 选文件 / 拖文件 → 运行态导入（可轮询、可取消）→ 报告、重复项另存、失败项重试。
 * 切资料库时调用 `resetForLibrarySwitch`，避免上一库的失败清单串到新库。
 */
export function useDocumentImport({ activeLibrary, openLibrarySetup, reloadScopedData, onFinished }: Options) {
  const importRun = useImportRun();
  const [state, setState] = useState<DocumentImportState>(emptyDocumentImport);
  const inputRef = useRef<HTMLInputElement>(null);
  // 没有资料库时拖进来的文件：建好库后自动导入。
  const pendingFiles = useRef<File[]>([]);
  const pendingDuplicates = useRef<File[]>([]);
  const pendingRetries = useRef<File[]>([]);

  const upload = useCallback(async (files: File[], duplicateStrategy: "keep_existing" | "save_copy" = "keep_existing") => {
    setState((current) => ({ ...current, importing: true, notice: "", error: "", duplicateCount: duplicateStrategy === "save_copy" ? 0 : current.duplicateCount }));
    try {
      // E8：导入走**运行态**（可轮询进度、可取消），不再是黑盒的一次性 POST。
      const result = await importRun.start(files, duplicateStrategy);
      if (!result) throw new Error("导入没有返回结果。");
      const duplicates = result.duplicates || [];
      if (duplicateStrategy === "keep_existing") {
        const duplicateNames = new Set(duplicates.map((item) => item.filename));
        pendingDuplicates.current = files.filter((file) => duplicateNames.has(file.name));
      } else {
        pendingDuplicates.current = [];
      }
      const batch = result.results || [];
      // E8：留下"需要处理"的那几份文件对象，重试按钮才有真东西可重发。
      const problematic = new Set(
        batch
          .filter((item) => item.status === "rejected" || item.status === "cancelled"
            || (item.status === "imported" && !item.searchable))
          .map((item) => item.filename),
      );
      pendingRetries.current = files.filter((file) => problematic.has(file.name));
      setState((current) => ({
        ...current,
        notice: describeDocumentImport(result),
        duplicateCount: duplicates.length,
        results: batch,
        version: current.version + 1,
      }));
      await reloadScopedData();
    } catch (reason) {
      setState((current) => ({
        ...current,
        error: toErrorMessage(reason, "资料导入失败。"),
        // W1 E1：把 code 一起留下，界面才能说"下一步"（换格式 / 去设置 / 稍后重试）。
        errorCode: errorCodeOf(reason),
      }));
    } finally {
      setState((current) => ({ ...current, importing: false }));
      onFinished();
    }
  }, [importRun, reloadScopedData, onFinished]);

  const importDroppedFiles = useCallback((files: File[]) => {
    if (!files.length) return;
    if (!activeLibrary) {
      pendingFiles.current = files;
      openLibrarySetup({ initialMode: "create", importCount: files.length });
      return;
    }
    void upload(files);
  }, [activeLibrary, openLibrarySetup, upload]);

  /** E8：重试这次"需要处理"的那几份（复用导入通道：字节已在库里的会走补索引路径）。 */
  const retryFailedImports = useCallback(() => {
    const files = pendingRetries.current;
    pendingRetries.current = [];
    if (files.length) void upload(files);
  }, [upload]);

  const dismissImportReport = useCallback(() => {
    pendingRetries.current = [];
    setState((current) => ({ ...current, results: null }));
  }, []);

  const importDuplicatesAsCopies = useCallback(() => {
    const files = pendingDuplicates.current;
    pendingDuplicates.current = [];
    if (files.length) void upload(files, "save_copy");
  }, [upload]);

  const startDocumentImport = useCallback(() => {
    pendingDuplicates.current = [];
    setState((current) => ({ ...current, notice: "", error: "", duplicateCount: 0 }));
    inputRef.current?.click();
  }, []);

  const selectDocumentsForImport = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;
    if (!activeLibrary) {
      pendingFiles.current = files;
      openLibrarySetup({ initialMode: "create", importCount: files.length });
      return;
    }
    await upload(files);
  }, [activeLibrary, openLibrarySetup, upload]);

  /** 用户取消新建资料库：等着导入的文件一起放弃。 */
  const discardPendingFiles = useCallback(() => { pendingFiles.current = []; }, []);

  /** W1 E1：导入报告、通知与"可重试文件"都属于**上一个**资料库 —— 不清就会串库。 */
  const resetForLibrarySwitch = useCallback(() => {
    setState(clearImportReport);
    pendingRetries.current = [];
  }, []);

  // 资料库建好之后，把之前拖进来的文件导进去。
  const activeLibraryId = activeLibrary?.library_id || null;
  useEffect(() => {
    if (!activeLibraryId || !pendingFiles.current.length) return;
    const files = pendingFiles.current;
    pendingFiles.current = [];
    void upload(files);
  }, [activeLibraryId, upload]);

  return {
    state,
    importRun,
    inputRef,
    canRetry: pendingRetries.current.length > 0,
    importing: state.importing || importRun.running,
    importDroppedFiles,
    retryFailedImports,
    dismissImportReport,
    importDuplicatesAsCopies,
    startDocumentImport,
    selectDocumentsForImport,
    discardPendingFiles,
    resetForLibrarySwitch,
  };
}
