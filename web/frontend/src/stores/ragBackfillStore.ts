import { create } from "zustand";

import { api } from "../lib/api";
import type { RagBackfillJob, RagSettingsResponse } from "../types";
import { useNoticeStore } from "./noticeStore";

interface RagBackfillState {
  job: RagBackfillJob | null;
  latestRag: RagSettingsResponse | null;
  polling: boolean;
  start: (rebuild: boolean) => Promise<RagBackfillJob | null>;
  syncStatus: () => Promise<RagBackfillJob | null>;
  cancel: () => Promise<void>;
  stopPolling: () => void;
  reset: () => void;
}

let pollTimer: number | null = null;

function clearPollTimer() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function notifyCompletion(job: RagBackfillJob) {
  const push = useNoticeStore.getState().pushNotice;
  if (job.status === "completed") {
    const errors = job.error_samples?.length || 0;
    if (errors > 0) {
      push({
        tone: "info",
        message: `向量索引已完成 ${job.backfilled} 份（${errors} 份失败，可在「检索与 RAG」查看详情）。`,
      });
      return;
    }
    push({
      tone: "success",
      message: job.rebuild
        ? `已完成 ${job.backfilled} 份资料向量重建，混合检索已就绪。`
        : `已补建 ${job.backfilled} 份资料向量，混合检索已就绪。`,
    });
    return;
  }
  if (job.status === "cancelled") {
    push({
      tone: "info",
      message: `已停止向量索引（已完成 ${job.backfilled} 份，未处理部分保留待建）。`,
    });
    return;
  }
  if (job.status === "failed") {
    push({
      tone: "error",
      message: `后台向量索引失败：${job.error || "请检查向量模型配置"}`,
    });
  }
}

export const useRagBackfillStore = create<RagBackfillState>()((set, get) => {
  function ensurePolling() {
    if (pollTimer !== null) return;
    set({ polling: true });
    pollTimer = window.setInterval(() => {
      void get().syncStatus();
    }, 650);
  }

  return {
    job: null,
    latestRag: null,
    polling: false,

    async start(rebuild: boolean) {
      if (typeof api.startRagBackfill !== "function") {
        // Fallback for minimal API test mocks that only stub synchronous backfillRagVectors
        const res = await api.backfillRagVectors(rebuild);
        const synthetic: RagBackfillJob = {
          job_id: "sync",
          status: "completed",
          rebuild: res.result.rebuilt,
          done: res.rag.status.vector_stats.vector_indexed,
          total: res.rag.status.vector_stats.documents,
          backfilled: res.result.backfilled,
          current_title: "",
          dim: res.result.dim,
          model: res.result.model,
          error: "",
          cancelled: false,
          vector_stats: res.result.vector_stats,
          error_samples: res.result.error_samples,
        };
        set({ job: synthetic, latestRag: res.rag, polling: false });
        notifyCompletion(synthetic);
        return synthetic;
      }
      const res = await api.startRagBackfill(rebuild);
      set({ job: res.job, latestRag: res.rag });
      if (res.job.status === "running") {
        ensurePolling();
      } else {
        clearPollTimer();
        set({ polling: false });
        if (res.job.status !== "idle") notifyCompletion(res.job);
      }
      return res.job;
    },

    async syncStatus() {
      if (typeof api.ragBackfillStatus !== "function") return null;
      try {
        const previousStatus = get().job?.status;
        const res = await api.ragBackfillStatus();
        const nextJob = res.job;
        set({ job: nextJob, latestRag: res.rag });
        if (nextJob.status === "running") {
          ensurePolling();
        } else {
          clearPollTimer();
          set({ polling: false });
          if (previousStatus === "running" && nextJob.status !== "idle") {
            notifyCompletion(nextJob);
          }
        }
        return nextJob;
      } catch {
        clearPollTimer();
        set({ polling: false });
        return null;
      }
    },

    async cancel() {
      if (typeof api.cancelRagBackfill !== "function") return;
      try {
        const res = await api.cancelRagBackfill();
        set({ job: res.job, latestRag: res.rag });
      } catch {
        // Keep polling so state settles truthfully
      }
    },

    stopPolling() {
      clearPollTimer();
      set({ polling: false });
    },

    reset() {
      clearPollTimer();
      set({ job: null, latestRag: null, polling: false });
    },
  };
});
