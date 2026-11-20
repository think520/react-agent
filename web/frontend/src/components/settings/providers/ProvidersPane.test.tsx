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
};

beforeEach(() => {
  vi.mocked(api.providerPresets).mockResolvedValue({ presets: [] });
  vi.mocked(api.fetchProviderModels).mockRejectedValue(new Error("服务未提供模型列表接口"));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProvidersPane model discovery", () => {
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
});
