import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import { CandidateReviewPanel } from "./CandidateReviewPanel";

/**
 * W1 E16：确认新概念之后，界面要能知道**确认出了哪些节点**（据此高亮几秒）。
 * 后端已经在确认响应里带上坐标与 placed；这里钉住前端把 id 交出去的这一步。
 */

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, graphCandidates: vi.fn(), graphCandidateAction: vi.fn(), graphConfirmCandidates: vi.fn() },
  };
});

const candidate = {
  candidate_id: "c-1",
  name: "注意力机制",
  level: "core",
  confidence: "high",
  definition: "注意力机制",
  excerpt: "……",
  suggested_rels: [],
};

beforeEach(() => {
  vi.mocked(api.graphCandidates).mockResolvedValue({ candidates: [candidate], count: 1 } as never);
  vi.mocked(api.graphCandidateAction).mockResolvedValue({
    concept: { concept_id: "c-1", name: "注意力机制", position: null, placed: false },
  } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("确认成功后把新概念的 id 交出去", async () => {
  const onConceptsConfirmed = vi.fn();
  render(<CandidateReviewPanel
    onClose={() => {}}
    onCandidatesChanged={() => {}}
    onConceptsConfirmed={onConceptsConfirmed}
  />);

  fireEvent.click(await screen.findByRole("button", { name: "确认" }));

  await waitFor(() => expect(onConceptsConfirmed).toHaveBeenCalledWith(["c-1"]));
});

it("批量确认也把这一批 id 都交出去", async () => {
  vi.mocked(api.graphConfirmCandidates).mockResolvedValue({
    concepts: [{ concept_id: "c-1" }, { concept_id: "c-2" }],
    relationships: [],
  } as never);
  const onConceptsConfirmed = vi.fn();
  render(<CandidateReviewPanel
    onClose={() => {}}
    onCandidatesChanged={() => {}}
    onConceptsConfirmed={onConceptsConfirmed}
  />);

  fireEvent.click(await screen.findByRole("button", { name: /全部确认/ }));

  await waitFor(() => expect(onConceptsConfirmed).toHaveBeenCalledWith(["c-1", "c-2"]));
});

it("拒绝不触发高亮（那不是新节点）", async () => {
  const onConceptsConfirmed = vi.fn();
  render(<CandidateReviewPanel
    onClose={() => {}}
    onCandidatesChanged={() => {}}
    onConceptsConfirmed={onConceptsConfirmed}
  />);

  fireEvent.click(await screen.findByRole("button", { name: "忽略" }));

  await waitFor(() => expect(api.graphCandidateAction).toHaveBeenCalled());
  expect(onConceptsConfirmed).not.toHaveBeenCalled();
});
