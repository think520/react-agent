import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProviderSummary } from "../types";
import { ModelSelect } from "./ModelSelect";
import { ProviderFormFields } from "./settings/providers/ProviderFormFields";
import type { ProviderForm } from "./settings/providers/providerForm";

const providers: ProviderSummary[] = [
  {
    name: "siliconflow",
    configured: true,
    model: "deepseek-ai/DeepSeek-V3",
    models: [
      { id: "deepseek-ai/DeepSeek-V3", name: "DeepSeek V3", kind: "chat" },
      { id: "BAAI/bge-m3", name: "BGE-M3", kind: "embedding" },
      { id: "BAAI/bge-reranker-v2-m3", name: "BGE Reranker", kind: "rerank" },
      { id: "Qwen/Qwen3-Embedding-8B", name: "Qwen3 Embedding" },
    ],
  },
];

afterEach(() => {
  cleanup();
});

describe("ModelSelect capability filtering", () => {
  it("shows only chat models by default and hides embedding/rerank models", () => {
    render(
      <ModelSelect
        providers={providers}
        value="siliconflow::deepseek-ai/DeepSeek-V3"
        onChange={() => {}}
        label="默认模型"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "默认模型" }));
    expect(screen.getByRole("option", { name: "DeepSeek V3" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "BGE-M3" })).toBeNull();
    expect(screen.queryByRole("option", { name: "BGE Reranker" })).toBeNull();
    expect(screen.queryByRole("option", { name: "Qwen3 Embedding" })).toBeNull();
  });

  it("toggles model kind in ProviderFormFields and hides set-default on embedding rows", () => {
    const setForm = vi.fn();
    const form: ProviderForm = {
      name: "siliconflow",
      base_url: "https://api.siliconflow.cn/v1",
      api_key: "",
      model_default: "deepseek-ai/DeepSeek-V3",
      models: [
        { id: "deepseek-ai/DeepSeek-V3", name: "DeepSeek V3" },
        { id: "BAAI/bge-m3", name: "BGE-M3", kind: "embedding" },
      ],
    };

    render(
      <ProviderFormFields
        form={form}
        setForm={setForm}
        working={false}
        keyless={false}
        onFetchModels={() => {}}
        modelInput={{ id: "", name: "" }}
        setModelInput={() => {}}
        onAddModel={() => {}}
        onRemoveModel={() => {}}
      />,
    );

    const chatButtons = screen.getAllByRole("button", { name: "对话" });
    expect(chatButtons.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: "向量" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "设为默认" })).toBeNull();

    fireEvent.click(chatButtons[0]);
    expect(setForm).toHaveBeenCalledWith(expect.objectContaining({
      model_default: "",
    }));
  });
});
