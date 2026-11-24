import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../../lib/api";
import type { ProviderSummary } from "../../../types";
import { ProvidersPane } from "./ProvidersPane";

vi.mock("../../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, providerPresets: vi.fn(), fetchProviderModels: vi.fn() },
  };
});

const provider: ProviderSummary = {
  name: "custom",
  configured: true,
  base_url: "https://api.example.com/v1",
  model: "model-known",
  models: [{ id: "model-known", name: "Known model" }],
  supports_embedding: true,
};

const secondProvider: ProviderSummary = {
  name: "deepseek",
  configured: true,
  base_url: "https://api.deepseek.com/v1",
  model: "deepseek-chat",
  models: [{ id: "deepseek-chat", name: "DeepSeek Chat" }],
  supports_embedding: false,
  embedding_note: "DeepSeek 仅用于对话生成。",
};

beforeEach(() => {
  vi.mocked(api.providerPresets).mockResolvedValue({ presets: [] });
  vi.mocked(api.fetchProviderModels).mockRejectedValue(new Error("服务未提供模型列表接口"));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProvidersPane model discovery & UX protections", () => {
  it("keeps existing models when the provider cannot list models", async () => {
    render(<ProvidersPane providers={[provider]} onChanged={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.click(screen.getByRole("button", { name: /读取模型/ }));

    expect(await screen.findByText("model-known")).toBeTruthy();
    expect(await screen.findByText(/服务未提供模型列表接口。可手动输入模型 ID。/)).toBeTruthy();
    expect(api.fetchProviderModels).toHaveBeenCalledWith("https://api.example.com/v1", undefined, "custom");
  });

  it("does not duplicate punctuation or manual-entry hint when backend message already provides one", async () => {
    vi.mocked(api.fetchProviderModels).mockRejectedValueOnce(
      new Error("该服务没有提供可用的 GET /models 接口。请确认 API 地址填写到服务根路径（例如 /v1），或手动添加服务商给出的模型 ID。"),
    );

    render(<ProvidersPane providers={[provider]} onChanged={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.click(screen.getByRole("button", { name: /读取模型/ }));

    const alert = await screen.findByText(/该服务没有提供可用的 GET \/models 接口/);
    expect(alert.textContent).not.toContain("。。");
    expect(alert.textContent).not.toContain("可手动输入模型 ID");
  });

  it("renders capability pills, exits clean edit on Escape without bubbling, and guards dirty switch", async () => {
    const outerKeyListener = vi.fn();
    window.addEventListener("keydown", outerKeyListener);
    try {
      render(<ProvidersPane providers={[provider, secondProvider]} onChanged={() => {}} />);
      expect(screen.getByText("对话 + 向量")).toBeTruthy();

      fireEvent.click(screen.getByRole("button", { name: "编辑" }));
      expect(screen.getByText("编辑 custom")).toBeTruthy();

      // Escape while clean exits edit mode and stops propagation to outer modal
      fireEvent.keyDown(window, { key: "Escape" });
      expect(screen.queryByText("编辑 custom")).toBeNull();
      expect(outerKeyListener).not.toHaveBeenCalled();

      // Dirty form guards switching providers
      fireEvent.click(screen.getByRole("button", { name: "编辑" }));
      const inputs = screen.getAllByRole("textbox");
      fireEvent.change(inputs[1], { target: { value: "https://changed.example.com/v1" } });
      fireEvent.click(screen.getAllByRole("button", { name: /deepseek/ })[0]);
      expect(await screen.findByText("放弃未保存的供应商修改？")).toBeTruthy();

      fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));
      expect(screen.getByText("仅对话")).toBeTruthy();
    } finally {
      window.removeEventListener("keydown", outerKeyListener);
    }
  });
});
