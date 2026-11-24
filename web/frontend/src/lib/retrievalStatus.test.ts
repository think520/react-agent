import { describe, expect, it } from "vitest";

import type { RagSettingsResponse, RuntimeStatus } from "../types";
import {
  formatEffectiveModeLabel,
  formatProviderCapability,
  formatRetrievalBadge,
  formatRetrieverChannel,
  formatRuntimeKnowledgeStatus,
  originOfUrl,
} from "./retrievalStatus";

function baseRag(overrides?: {
  config?: Partial<RagSettingsResponse["config"]>;
  status?: Partial<RagSettingsResponse["status"]>;
}): RagSettingsResponse {
  return {
    config: {
      mode: "custom",
      provider_name: "",
      preset: "siliconflow",
      base_url: "https://api.siliconflow.cn/v1",
      model: "BAAI/bge-m3",
      dim: 1024,
      ollama_url: "http://localhost:11434",
      ollama_model: "qwen3-embedding:0.6b",
      has_api_key: true,
      api_key_source: "saved",
      ...overrides?.config,
    },
    status: {
      knowledge_ready: true,
      effective_mode: "hybrid",
      configured_mode: "custom",
      embedding_available: true,
      provider_ready: true,
      active_provider: "openai_compat",
      display_provider: "siliconflow",
      active_model: "BAAI/bge-m3",
      active_dim: 1024,
      stored_signature: null,
      signature_mismatch: "",
      semantic_status: { code: "ok", title: "就绪", detail: "正常", action: "" },
      vector_stats: { documents: 10, chunks: 30, vector_indexed: 10, vector_pending: 0, vector_error: 0 },
      error_samples: [],
      sample_queries: [],
      needs_backfill: false,
      needs_rebuild: false,
      ...overrides?.status,
    },
    presets: [],
    reusable_providers: [],
  };
}

describe("retrievalStatus helpers", () => {
  it("normalizes OpenAI origins safely", () => {
    expect(originOfUrl("HTTPS://API.SiliconFlow.cn/v1/embeddings")).toBe("https://api.siliconflow.cn");
    expect(originOfUrl("http://localhost:11434/v1")).toBe("http://localhost:11434");
    expect(originOfUrl("not-a-url")).toBe("");
  });

  it("formats retrieval badge consistently across states", () => {
    expect(formatRetrievalBadge(null).label).toBe("读取中");
    expect(formatRetrievalBadge(baseRag({ status: { knowledge_ready: false } })).label).toBe("等待导入资料");
    expect(formatRetrievalBadge(baseRag({ status: { needs_rebuild: true, signature_mismatch: "模型变更" } }))).toMatchObject({
      tone: "warn",
      label: "待重建向量",
    });
    expect(formatRetrievalBadge(baseRag({
      status: {
        effective_mode: "hybrid",
        needs_backfill: true,
        vector_stats: { documents: 10, chunks: 30, vector_indexed: 7, vector_pending: 3, vector_error: 0 },
      },
    }))).toMatchObject({ tone: "warn", label: "还差 3 份向量" });
    expect(formatRetrievalBadge(baseRag({
      status: {
        effective_mode: "fts_only",
        embedding_available: true,
        needs_backfill: true,
      },
    }))).toMatchObject({ tone: "warn", label: "待补建向量" });
    expect(formatRetrievalBadge(baseRag())).toMatchObject({ tone: "ready", label: "混合检索已就绪" });
    expect(formatRetrievalBadge(baseRag({
      status: {
        effective_mode: "fts_only",
        configured_mode: "disabled",
        embedding_available: false,
      },
    }))).toMatchObject({ tone: "muted", label: "仅关键词检索" });
  });

  it("formats mode, retriever channel, provider capability, and runtime status", () => {
    expect(formatEffectiveModeLabel("hybrid")).toBe("混合检索（向量 + 关键词）");
    expect(formatEffectiveModeLabel("fts_only")).toBe("仅关键词检索");
    expect(formatEffectiveModeLabel("unavailable")).toBe("等待导入资料");

    expect(formatRetrieverChannel(["vector", "fts5"])).toEqual({ label: "语义 + 关键词双命中", isHybrid: true });
    expect(formatRetrieverChannel(["vector"])).toEqual({ label: "仅语义向量命中", isHybrid: false });
    expect(formatRetrieverChannel(["fts5"])).toEqual({ label: "仅关键词命中", isHybrid: false });

    expect(formatProviderCapability({ supports_embedding: true, embedding_note: "" })).toMatchObject({ badge: "对话 + 向量", tone: "hybrid" });
    expect(formatProviderCapability({ supports_embedding: false, embedding_note: "仅对话" })).toMatchObject({ badge: "仅对话", tone: "chat" });
    expect(formatProviderCapability({ supports_embedding: null, embedding_note: "" })).toMatchObject({ badge: "待确认", tone: "unknown" });

    const runtimeBase: RuntimeStatus = {
      backend: "connected",
      version: "0.1.0",
      active_library: null,
      knowledge: { state: "ready", documents: 12 },
      retrieval: { effective_mode: "hybrid", embedding_available: true, active_provider: "siliconflow", active_model: "BAAI/bge-m3", vector_indexed: 12, documents: 12 },
      memory: { enabled: true },
      skills: { enabled: 1, available: 2 },
      providers: { configured: 1, available: 2, default: "deepseek" },
      search: { default: "auto", permission: "ask", tavily_configured: false, exa_configured: true, jina_fallback: true },
    };
    expect(formatRuntimeKnowledgeStatus(runtimeBase)).toBe("12 份资料 · 混合检索");
    expect(formatRuntimeKnowledgeStatus({
      ...runtimeBase,
      retrieval: { ...runtimeBase.retrieval!, effective_mode: "fts_only" },
    })).toBe("12 份资料 · 仅关键词检索");
    expect(formatRuntimeKnowledgeStatus({
      ...runtimeBase,
      retrieval: { ...runtimeBase.retrieval!, effective_mode: "unavailable" },
    })).toBe("12 份资料 · 索引未就绪");
    expect(formatRuntimeKnowledgeStatus({
      ...runtimeBase,
      knowledge: { state: "empty", documents: 0 },
    })).toBe("等待资料");
  });
});
