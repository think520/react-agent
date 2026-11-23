import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../lib/api";
import { useHandoffStore } from "../stores/handoffStore";
import { ConceptSidebar } from "./ConceptSidebar";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: { ...actual.api, graphConcept: vi.fn(), conceptMastery: vi.fn(), graphState: vi.fn() } };
});

const detail = {
  concept: {
    concept_id: "c1", name: "Dijkstra 算法", level: "core", definition: "", aliases: [], topic_ids: [],
    note: "", created_at: 0, updated_at: 0, x: 0, y: 0,
  },
  relationships: [],
  evidence: {},
};

function renderSidebar() {
  return render(<MemoryRouter><ConceptSidebar conceptId="c1" onClose={() => undefined} /></MemoryRouter>);
}

beforeEach(() => {
  vi.mocked(api.graphConcept).mockResolvedValue(detail as never);
  vi.mocked(api.graphState).mockResolvedValue({ concepts: [] } as never);
});

afterEach(() => { cleanup(); vi.clearAllMocks(); useHandoffStore.getState().clearPracticeHandoff(); });

describe("掌握度读取失败不能冒充「尚未练习」（2026-11-11 审查）", () => {
  it("only a real mastery_not_found reads as never practiced", async () => {
    vi.mocked(api.conceptMastery).mockRejectedValue(new ApiError("未找到", "mastery_not_found", 404));
    renderSidebar();
    expect(await screen.findByText("尚未练习")).toBeTruthy();
  });

  it("any other failure says the mastery is temporarily unavailable", async () => {
    vi.mocked(api.conceptMastery).mockRejectedValue(new ApiError("boom", "request_failed", 500));
    renderSidebar();
    expect(await screen.findByText("暂时读不到掌握度")).toBeTruthy();
    expect(screen.queryByText("尚未练习")).toBeNull();
  });
});

it("clicking 生成练习题 hands off the concept name and navigates to /practice", async () => {
  vi.mocked(api.conceptMastery).mockRejectedValue(new ApiError("未找到", "mastery_not_found", 404));
  render(
    <MemoryRouter initialEntries={["/knowledge-map"]}>
      <Routes>
        <Route path="/practice" element={<div>Practice Screen</div>} />
        <Route path="*" element={<ConceptSidebar conceptId="c1" onClose={() => undefined} />} />
      </Routes>
    </MemoryRouter>,
  );

  fireEvent.click(await screen.findByRole("button", { name: /生成练习题/ }));
  expect(useHandoffStore.getState().practiceTopic).toBe("Dijkstra 算法");
  expect(screen.getByText("Practice Screen")).toBeTruthy();
});
