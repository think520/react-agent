import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import type { SettingsSummary } from "../types";
import { OnboardingDialog } from "./OnboardingDialog";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("OnboardingDialog connection status", () => {
  it("does not call a saved provider ready until a real connection test passes", async () => {
    vi.spyOn(api, "providerTest").mockResolvedValue({
      provider: "openai", model: "gpt-test", latency_ms: 42, response_received: true,
    });
    const settings = {
      default_provider: "openai",
      providers: [{ name: "openai", configured: true }],
    } as SettingsSummary;

    render(<OnboardingDialog settings={settings} documents={[]} selectedDocumentIds={[]} onToggleDocument={() => {}} onComplete={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));

    expect(screen.getByText("配置已保存，但尚未验证连接。")).toBeTruthy();
    expect(screen.queryByText(/连接正常/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await waitFor(() => expect(screen.getByText("42ms · 连接正常，可以开始对话和出题。")).toBeTruthy());
    expect(api.providerTest).toHaveBeenCalledWith("openai");
  });
});
