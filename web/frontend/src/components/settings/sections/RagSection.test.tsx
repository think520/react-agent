import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../../lib/api";
import { useNoticeStore } from "../../../stores/noticeStore";
import { useRagBackfillStore } from "../../../stores/ragBackfillStore";
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
      startRagBackfill: vi.fn(),
      ragBackfillStatus: vi.fn(),
      cancelRagBackfill: vi.fn(),
      ragOllamaModels: vi.fn(),
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
      has_saved_custom_key: false,
      saved_custom_preset: "",
      saved_custom_base_url: "",
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
        title: "尚未开启向量检索（当前仅关键词）",
        detail: "还没有启用云端向量模型，本机 Ollama 也未启动。",
        action: "选择「云端向量模型」或启动本地 Ollama。",
      },
      vector_stats: { documents: 47, chunks: 180, vector_indexed: 0, vector_pending: 47, vector_error: 0 },
      error_samples: [],
      sample_queries: ["贪心算法", "动态规划"],
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
      {
        id: "custom",
        label: "自定义 OpenAI 兼容",
        badge: "任意网关",
        description: "自定义兼容接口。",
        base_url: "",
        default_model: "",
        dim: null,
        api_key_env: "",
        suggested_models: [],
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
  vi.mocked(api.ragOllamaModels).mockResolvedValue({
    ok: true,
    reachable: false,
    url: "http://localhost:11434",
    models: [],
    embedding_models: [],
    error: "offline",
  });
});

afterEach(() => {
  cleanup();
  useRagBackfillStore.getState().reset();
  useNoticeStore.getState().clearNotices();
  vi.clearAllMocks();
});

describe("RagSection 3-mode UX, auto-reuse, background backfill & hit test", () => {
  it("shows 3 modes, disables save when clean, collapses empty search card, and normalizes tested URL", async () => {
    const emptyRag = makeRagResponse({
      status: {
        ...makeRagResponse().status,
        knowledge_ready: false,
        effective_mode: "unavailable",
        vector_stats: { documents: 0, chunks: 0, vector_indexed: 0, vector_pending: 0, vector_error: 0 },
        sample_queries: [],
      },
    });
    vi.mocked(api.ragSettings).mockResolvedValueOnce(emptyRag);
    vi.mocked(api.testRagEmbedding).mockResolvedValueOnce({
      ok: true,
      provider: "openai_compat",
      model: "BAAI/bge-m3",
      dim: 1024,
      latency_ms: 140,
      normalized_base_url: "https://api.example.com/v1",
      url_normalized: true,
    });

    render(<RagSection />);
    expect(await screen.findByText("尚未开启向量检索（当前仅关键词）")).toBeTruthy();
    expect(screen.getByText(/当前资料库还没有文档/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "当前配置已生效" }).hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByRole("radio", { name: /云端向量模型/ }));
    fireEvent.click(screen.getByRole("button", { name: /自定义 OpenAI 兼容/ }));
    fireEvent.change(screen.getByPlaceholderText("https://example.com/v1"), {
      target: { value: "https://api.example.com/v1/embeddings" },
    });
    fireEvent.change(screen.getByPlaceholderText("如 BAAI/bge-m3"), {
      target: { value: "BAAI/bge-m3" },
    });
    fireEvent.change(screen.getByPlaceholderText(/粘贴该平台的 API Key/), {
      target: { value: "sk-test-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "仅测试连通性" }));

    expect(await screen.findByText(/连接成功 · BAAI\/bge-m3 · 1024 维 · 140ms（已自动清理接口后缀）/)).toBeTruthy();
    expect((screen.getByPlaceholderText("https://example.com/v1") as HTMLInputElement).value).toBe("https://api.example.com/v1");
  });

  it("hides password input when reusing a configured provider key and lets user override or clear saved keys", async () => {
    const ragWithProvider = makeRagResponse({
      config: {
        ...makeRagResponse().config,
        mode: "custom",
        has_api_key: true,
        api_key_source: "saved",
        has_saved_custom_key: true,
        saved_custom_base_url: "https://api.siliconflow.cn/v1",
      },
      status: {
        ...makeRagResponse().status,
        effective_mode: "hybrid",
        embedding_available: true,
        provider_ready: true,
        semantic_status: { code: "ok", title: "混合检索已就绪（向量 + 全文）", detail: "已可用。", action: "" },
        vector_stats: { documents: 47, chunks: 180, vector_indexed: 47, vector_pending: 0, vector_error: 0 },
      },
    });
    vi.mocked(api.ragSettings).mockResolvedValueOnce(ragWithProvider);

    render(<RagSection />);
    await screen.findByText("已保存该接口的专用 API Key，无需重复输入");
    expect(screen.queryByPlaceholderText(/粘贴该平台的 API Key/)).toBeNull();

    const clearBtn = screen.getByRole("button", { name: "清除已存密钥" });
    fireEvent.click(clearBtn);
    expect(screen.getByRole("button", { name: /将清除已存密钥/ }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /将清除已存密钥/ }));
    expect(screen.getByRole("button", { name: "清除已存密钥" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "改用其它密钥" }));
    expect(screen.getByPlaceholderText(/粘贴该平台的 API Key/)).toBeTruthy();
  });

  it("supports test-then-save + background backfill with stop + undo + sample hit test chips", async () => {
    const updatedRag = makeRagResponse({
      config: {
        ...makeRagResponse().config,
        mode: "custom",
        has_api_key: true,
        api_key_source: "saved",
      },
      status: {
        ...makeRagResponse().status,
        configured_mode: "custom",
        embedding_available: true,
        provider_ready: true,
        needs_backfill: true,
        semantic_status: { code: "no_vectors_indexed", title: "向量模型已就绪，但资料尚未建向量索引", detail: "待建", action: "" },
      },
    });
    vi.mocked(api.testRagEmbedding).mockResolvedValueOnce({
      ok: true,
      provider: "openai_compat",
      model: "BAAI/bge-m3",
      dim: 1024,
      latency_ms: 95,
    });
    vi.mocked(api.saveRagSettings).mockResolvedValue(updatedRag);
    vi.mocked(api.startRagBackfill).mockResolvedValueOnce({
      ok: true,
      job: {
        job_id: "bf_1",
        status: "running",
        rebuild: false,
        done: 12,
        total: 47,
        backfilled: 12,
        current_title: "greedy.md",
        dim: 1024,
        model: "BAAI/bge-m3",
        error: "",
        cancelled: false,
      },
      rag: updatedRag,
    });
    vi.mocked(api.cancelRagBackfill).mockResolvedValueOnce({
      ok: true,
      job: {
        job_id: "bf_1",
        status: "cancelled",
        rebuild: false,
        done: 12,
        total: 47,
        backfilled: 12,
        current_title: "",
        dim: 1024,
        model: "BAAI/bge-m3",
        error: "",
        cancelled: true,
      },
      rag: updatedRag,
    });
    vi.mocked(api.testRagSearch).mockResolvedValueOnce({
      ok: true,
      query: "贪心算法",
      latency_ms: 28,
      retrieval_mode: "hybrid",
      resolved_mode: "hybrid",
      semantic_available: true,
      semantic_reason: null,
      results: [{
        chunk_id: "c1",
        document_id: "d1",
        title: "贪心算法",
        source: "raw/greedy.md",
        heading_text: "交换论证",
        collection: "material",
        score: 0.912,
        retrievers: ["vector", "fts5"],
        snippet: "每一步都选择局部最优。",
      }],
    });

    render(<RagSection />);
    await screen.findByText("尚未开启向量检索（当前仅关键词）");

    fireEvent.click(screen.getByRole("radio", { name: /云端向量模型/ }));
    fireEvent.change(screen.getByPlaceholderText(/粘贴该平台的 API Key/), { target: { value: "sk-new-123" } });
    fireEvent.click(screen.getByRole("button", { name: /测试并保存，补建 47 份向量/ }));

    expect(await screen.findByText(/正在后台补建向量 · 12\/47 份/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "撤销更改" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "停止" }));
    await waitFor(() => {
      expect(api.cancelRagBackfill).toHaveBeenCalled();
    });

    // Click sample query chip -> triggers hit test & displays #1 rank + dual-channel pill + Clear button
    fireEvent.click(screen.getByRole("button", { name: "贪心算法" }));
    expect(await screen.findByText("#1")).toBeTruthy();
    expect(screen.getByText("语义 + 关键词双命中")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "清空" }));
    expect(screen.queryByText("#1")).toBeNull();
  });

  it("discovers Ollama models automatically and saves disabled mode without destructive modal", async () => {
    const indexedRag = makeRagResponse({
      config: { ...makeRagResponse().config, mode: "custom", has_api_key: true, api_key_source: "saved" },
      status: {
        ...makeRagResponse().status,
        effective_mode: "hybrid",
        configured_mode: "custom",
        embedding_available: true,
        provider_ready: true,
        stored_signature: { provider: "openai_compat", model: "BAAI/bge-m3", dim: 1024 },
        semantic_status: { code: "ok", title: "混合检索已就绪（向量 + 全文）", detail: "已就绪", action: "" },
        vector_stats: { documents: 10, chunks: 30, vector_indexed: 10, vector_pending: 0, vector_error: 0 },
      },
    });
    vi.mocked(api.ragSettings).mockResolvedValueOnce(indexedRag);
    vi.mocked(api.saveRagSettings).mockResolvedValueOnce({
      ...indexedRag,
      config: { ...indexedRag.config, mode: "disabled", has_api_key: false, api_key_source: "none" },
    });
    vi.mocked(api.ragOllamaModels).mockResolvedValueOnce({
      ok: true,
      reachable: true,
      url: "http://localhost:11434",
      models: [{ name: "bge-m3:latest", kind: "embedding", is_embedding: true, size_label: "1.2 GB" }],
      embedding_models: ["bge-m3:latest"],
      error: "",
    });

    render(<RagSection />);
    await screen.findByText("混合检索已就绪（向量 + 全文）");

    // Switching to Ollama discovers running embedding models
    fireEvent.click(screen.getByRole("radio", { name: /本地 Ollama/ }));
    expect(await screen.findByRole("button", { name: /bge-m3:latest · 1.2 GB/ })).toBeTruthy();

    // Switching to disabled saves immediately with zero rebuild confirmation modal
    fireEvent.click(screen.getByRole("radio", { name: /仅关键词检索/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
    await waitFor(() => {
      expect(api.saveRagSettings).toHaveBeenCalledWith(expect.objectContaining({ mode: "disabled" }));
    });
  });
});
