import type {
  ProviderModel,
  RagSettingsResponse,
  RagStatusSummary,
  RuntimeStatus,
} from "../types";

export interface RetrievalBadgeSummary {
  tone: "ready" | "warn" | "muted";
  label: string;
  detail: string;
}

export interface ProviderCapabilitySummary {
  badge: string;
  tone: "hybrid" | "chat" | "unknown";
  note: string;
}

/** Normalize an OpenAI-compatible URL to lowercase scheme://host origin for key reuse checks. */
export function originOfUrl(rawUrl: string): string {
  const trimmed = (rawUrl || "").trim();
  if (!trimmed) return "";
  try {
    const parsed = new URL(trimmed);
    return `${parsed.protocol.toLowerCase()}//${parsed.host.toLowerCase()}`;
  } catch {
    return "";
  }
}

/** Single truth-source formatter for RAG status badges across ModelsSection, RagSection, and StatusSection. */
export function formatRetrievalBadge(rag: RagSettingsResponse | null): RetrievalBadgeSummary {
  if (!rag) {
    return { tone: "muted", label: "读取中", detail: "正在读取检索状态…" };
  }
  const { status } = rag;
  const stats = status.vector_stats;
  if (!status.knowledge_ready || stats.documents === 0) {
    if (status.provider_ready) {
      return {
        tone: "muted",
        label: "等待导入资料",
        detail: `向量模型已就绪（${status.display_provider || status.active_provider} · ${status.active_model}），导入资料后将自动建立向量`,
      };
    }
    return {
      tone: "muted",
      label: "等待导入资料",
      detail: "导入并同步学习资料后可开启混合检索与召回测试",
    };
  }
  if (status.needs_rebuild || status.signature_mismatch) {
    return {
      tone: "warn",
      label: "待重建向量",
      detail: status.signature_mismatch || "向量模型已切换，需重建向量索引以恢复语义检索",
    };
  }
  const pendingCount = (stats.vector_pending || 0) + (stats.vector_error || 0);
  if (status.effective_mode === "hybrid") {
    if (status.needs_backfill && pendingCount > 0) {
      return {
        tone: "warn",
        label: `还差 ${pendingCount} 份向量`,
        detail: `已启用混合检索（${stats.vector_indexed}/${stats.documents} 份已建向量，仍有 ${pendingCount} 份待补建）`,
      };
    }
    return {
      tone: "ready",
      label: "混合检索已就绪",
      detail: `已启用：${status.display_provider || status.active_provider} · ${status.active_model}`,
    };
  }
  if (status.embedding_available && status.needs_backfill) {
    return {
      tone: "warn",
      label: "待补建向量",
      detail: `模型已就绪（${status.display_provider || status.active_provider} · ${status.active_model}），需为已有 ${stats.documents} 份资料补建向量`,
    };
  }
  return {
    tone: "muted",
    label: "仅关键词检索",
    detail: status.configured_mode === "disabled"
      ? "当前已设为仅使用关键词检索（资料不发送至外部向量服务）"
      : "尚未启用可用的向量模型（当前仅关键词检索；DeepSeek/MiniMax 等纯对话接口不提供向量化）",
  };
}

/** Human-readable retrieval mode label for metrics & search-test summary. */
export function formatEffectiveModeLabel(mode: RagStatusSummary["effective_mode"] | string): string {
  if (mode === "hybrid") return "混合检索（向量 + 关键词）";
  if (mode === "fts_only") return "仅关键词检索";
  return "等待导入资料";
}

/** Human-readable hit channel tag shared by search test & diagnostics. */
export function formatRetrieverChannel(retrievers: string[]): { label: string; isHybrid: boolean } {
  const hasVec = retrievers.includes("vector");
  const hasFts = retrievers.some((item) => item === "fts5" || item === "fts" || item === "keyword");
  if (hasVec && hasFts) return { label: "语义 + 关键词双命中", isHybrid: true };
  if (hasVec) return { label: "仅语义向量命中", isHybrid: false };
  return { label: "仅关键词命中", isHybrid: false };
}

/** Consistent provider capability summary shared across ProvidersPane and RagSection. */
export function formatProviderCapability(
  provider: { supports_embedding?: boolean | null; embedding_note?: string | null; models?: ProviderModel[] },
): ProviderCapabilitySummary {
  const hasEmbModel = Boolean(provider.models?.some((model) => model.kind === "embedding"));
  if (provider.supports_embedding === true || hasEmbModel) {
    return {
      badge: "对话 + 向量",
      tone: "hybrid",
      note: "同时支持对话与向量接口，开启「云端向量模型」后可直接复用这里保存的密钥。",
    };
  }
  if (provider.supports_embedding === false) {
    return {
      badge: "仅对话",
      tone: "chat",
      note: provider.embedding_note || "该平台仅用于对话与 Wiki 生成，官方不提供向量接口。",
    };
  }
  return {
    badge: "待确认",
    tone: "unknown",
    note: "若该兼容网关提供 /embeddings 接口，也可在「检索与 RAG → 云端向量模型」填写其根路径和密钥。",
  };
}

/** Unified knowledge retrieval summary for StatusSection. */
export function formatRuntimeKnowledgeStatus(runtimeStatus: RuntimeStatus): string {
  if (runtimeStatus.knowledge.state !== "ready") return "等待资料";
  const mode = runtimeStatus.retrieval?.effective_mode;
  let modeText = "";
  if (mode === "hybrid") modeText = " · 混合检索";
  else if (mode === "fts_only") modeText = " · 仅关键词检索";
  else if (mode === "unavailable") modeText = " · 索引未就绪";
  return `${runtimeStatus.knowledge.documents} 份资料${modeText}`;
}
