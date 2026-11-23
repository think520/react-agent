import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../../lib/api";
import type { RagSettingsResponse } from "../../../types";
import { RagSection } from "./RagSection";

vi.mock("../../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      ragSettings: vi.fn(),
      saveRagSettings: vi.fn(),
      testRagEmbedding: vi.fn(),
      backfillRagVectors: vi.fn(),
      testRagSearch: vi.fn(),
    },
  };
});

function makeRagResponse(overrides?: Partial<RagSettingsResponse>): RagSettingsResponse {
  return {
    config: {
      mode: "auto",
      provider_name: "",
      preset: "siliconflow",
      base_url: "https://api.siliconflow.cn/v1",
      model: "BAAI/bge-m3",
      dim: 1024,
      ollama_url: "http://localhost:11434",
      ollama_model: "qwen3-embedding:0.6b",
      has_api_key: false,
      api_key_source: "none",
    },
    status: {
      knowledge_ready: true,
      effective_mode: "fts_only",
      configured_mode: "auto",
      embedding_available: false,
      provider_ready: false,
      active_provider: "ollama",
      display_provider: "ollama",
      active_model: "qwen3-embedding:0.6b",
      active_dim: null,
      stored_signature: null,
      signature_mismatch: "",
      semantic_status: {
        code: "embedding_not_configured",
        title: "尚未开启向量检索（当前仅纯文本）",
        detail: "还没有在设置中启用可用的云端向量密钥，本机 Ollama 也未启动。",
        action: "选择硅基流动 BGE-M3 或启动本地 Ollama。",
      },
      vector_stats: { documents: 47, chunks: 180, vector_indexed: 0, vector_pending: 47, vector_error: 0 },
      error_samples: [],
      needs_backfill: false,
      needs_rebuild: false,
    },
    presets: [
      {
        id: "siliconflow",
        label: "硅基流动（SiliconFlow）",
        badge: "推荐 · BGE-M3 免费可用",
        description: "支持 BAAI/bge-m3。",
        base_url: "https://api.siliconflow.cn/v1",
        default_model: "BAAI/bge-m3",
        dim: 1024,
        api_key_env: "SILICONFLOW_API_KEY",
        suggested_models: ["BAAI/bge-m3", "Qwen/Qwen3-Embedding-8B"],
      },
    ],
    reusable_providers: [
      {
        name: "deepseek",
        preset: "deepseek",
        configured: true,
        keyless: false,
        base_url: "https://api.deepseek.com/v1",
        supports_embedding: false,
        embedding_note: "DeepSeek 官方暂不提供向量 API。",
        embedding_models: [],
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(api.ragSettings).mockResolvedValue(makeRagResponse());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RagSection guidance, configuration, backfill and hit test", () => {
  it("shows role primer, real fts_only status, and lets user test embedding config", async () => {
    vi.mocked(api.testRagEmbedding).mockResolvedValue({
      ok: true,
      provider: "openai_compat",
      model: "BAAI/bge-m3",
      dim: 1024,
      latency_ms: 185,
    });

    render(<RagSection />);

    expect(await screen.findByText("尚未开启向量检索（当前仅纯文本）")).toBeTruthy();
    expect(screen.getByText(/DeepSeek 官方目前不提供向量接口/)).toBeTruthy();
    expect(screen.getByText("0 / 47 份已建向量")).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText(/粘贴该平台的 API Key/), { target: { value: "sk-test-123" } });
    fireEvent.click(screen.getByRole("button", { name: "测试向量模型" }));

    expect(await screen.findByText(/连接成功 · BAAI\/bge-m3 · 1024 维 · 185ms/)).toBeTruthy();
  });

  it("explains why DeepSeek cannot be reused under provider mode and supports backfill + search test", async () => {
    const readyRag = makeRagResponse({
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
      },
      status: {
        knowledge_ready: true,
        effective_mode: "fts_only",
        configured_mode: "custom",
        embedding_available: true,
        provider_ready: true,
        active_provider: "openai_compat",
        display_provider: "siliconflow",
        active_model: "BAAI/bge-m3",
        active_dim: 1024,
        stored_signature: null,
        signature_mismatch: "",
        semantic_status: {
          code: "no_vectors_indexed",
          title: "向量模型已就绪，但资料尚未建向量索引",
          detail: "目前尚未生成向量（0/47）。",
          action: "点击补建向量。",
        },
        vector_stats: { documents: 47, chunks: 180, vector_indexed: 0, vector_pending: 47, vector_error: 0 },
        error_samples: [],
        needs_backfill: true,
        needs_rebuild: false,
      },
    });
    const indexedRag = makeRagResponse({
      ...readyRag,
      status: {
        ...readyRag.status,
        effective_mode: "hybrid",
        vector_stats: { documents: 47, chunks: 180, vector_indexed: 47, vector_pending: 0, vector_error: 0 },
        needs_backfill: false,
        semantic_status: {
          code: "ok",
          title: "混合检索已就绪（向量 + 全文）",
          detail: "向量与全文检索均可用。",
          action: "",
        },
      },
    });
    vi.mocked(api.ragSettings).mockResolvedValueOnce(readyRag);
    vi.mocked(api.backfillRagVectors).mockResolvedValueOnce({
      ok: true,
      result: { ok: true, rebuilt: false, backfilled: 47, dim: 1024, model: "BAAI/bge-m3", vector_stats: indexedRag.status.vector_stats, error_samples: [] },
      rag: indexedRag,
    });
    vi.mocked(api.testRagSearch).mockResolvedValueOnce({
      ok: true,
      query: "局部最优",
      latency_ms: 42,
      retrieval_mode: "hybrid",
      resolved_mode: "hybrid",
      semantic_available: true,
      semantic_reason: null,
      results: [{
        chunk_id: "c1",
        document_id: "d1",
        title: "贪心算法",
        source: "raw/greedy.md",
        heading_text: "基本性质",
        collection: "material",
        score: 0.912,
        retrievers: ["vector", "fts5"],
        snippet: "每一步选局部最优。",
      }],
    });

    render(<RagSection />);
    await screen.findByText("向量模型已就绪，但资料尚未建向量索引");

    fireEvent.click(screen.getByRole("button", { name: /为 47 份资料补建向量/ }));
    expect(await screen.findByText("47 / 47 份已建向量")).toBeTruthy();

    fireEvent.click(screen.getByRole("radio", { name: "复用已有供应商" }));
    expect(screen.getByText(/已配置的 deepseek 仅支持对话生成/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("召回测试关键词"), { target: { value: "局部最优" } });
    fireEvent.click(screen.getByRole("button", { name: "测试召回" }));

    await waitFor(() => {
      expect(screen.getByText("实际模式：hybrid（向量 + 全文融合）")).toBeTruthy();
      expect(screen.getByText("向量 + 全文双路命中")).toBeTruthy();
      expect(screen.getByText("贪心算法")).toBeTruthy();
    });
  });

  it("asks for confirmation when switching away from an already-indexed embedding model", async () => {
    const indexedRag = makeRagResponse({
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
        stored_signature: { provider: "openai_compat", model: "BAAI/bge-m3", dim: 1024 },
        signature_mismatch: "",
        semantic_status: { code: "ok", title: "混合检索已就绪（向量 + 全文）", detail: "可用", action: "" },
        vector_stats: { documents: 10, chunks: 30, vector_indexed: 10, vector_pending: 0, vector_error: 0 },
        error_samples: [],
        needs_backfill: false,
        needs_rebuild: false,
      },
    });
    vi.mocked(api.ragSettings).mockResolvedValueOnce(indexedRag);
    vi.mocked(api.saveRagSettings).mockResolvedValueOnce(indexedRag);

    render(<RagSection />);
    await screen.findByText("混合检索已就绪（向量 + 全文）");

    fireEvent.click(screen.getByRole("radio", { name: "仅纯文本" }));
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));

    expect(await screen.findByText("切换向量模型将使旧向量暂停生效")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存并继续" }));

    await waitFor(() => {
      expect(api.saveRagSettings).toHaveBeenCalledWith(expect.objectContaining({ mode: "disabled" }));
    });
  });
});
