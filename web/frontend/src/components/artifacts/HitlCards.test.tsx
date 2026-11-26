import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MemoryConfirmationCard } from "./MemoryConfirmationCard";
import { SettingsChangeCard } from "./SettingsChangeCard";
import { WebConsentCard } from "./WebConsentCard";

afterEach(cleanup);

describe("HITL decision cards unified data-state and actions", () => {
  it("renders WebConsentCard states and resolves actions", () => {
    const onResolve = vi.fn();
    const pending = {
      type: "web_consent" as const,
      artifact_id: "w1",
      search_id: "s1",
      query: "FlashAttention v3",
      reason: "本地资料未包含该论文。",
      status: "pending" as const,
    };
    const { container, rerender } = render(<WebConsentCard artifact={pending} busy={false} onResolve={onResolve} />);
    expect(container.querySelector(".hitl-card")?.getAttribute("data-state")).toBe("pending");
    fireEvent.click(screen.getByRole("button", { name: "联网查找" }));
    expect(onResolve).toHaveBeenCalledWith(pending, "approve");

    rerender(<WebConsentCard artifact={{ ...pending, status: "approved" }} busy={false} onResolve={onResolve} />);
    expect(container.querySelector(".hitl-card")?.getAttribute("data-state")).toBe("approved");
    expect(screen.getByText("已同意联网查找")).toBeInTheDocument();
  });

  it("renders MemoryConfirmationCard and SettingsChangeCard data-state transitions", () => {
    const mem = {
      type: "memory_confirmation" as const,
      artifact_id: "m1",
      scope: "library" as const,
      kind: "course_insight" as const,
      title: "优先直觉",
      content: "先看直觉示例再推公式。",
      requires_warning: false,
      status: "pending" as const,
    };
    const { container, rerender } = render(<MemoryConfirmationCard artifact={mem} busy={false} onResolve={vi.fn()} />);
    expect(container.querySelector(".hitl-card")?.getAttribute("data-state")).toBe("pending");
    rerender(<MemoryConfirmationCard artifact={{ ...mem, status: "confirmed" }} busy={false} onResolve={vi.fn()} />);
    expect(container.querySelector(".hitl-card")?.getAttribute("data-state")).toBe("approved");

    const settingsArt = {
      type: "settings_change" as const,
      artifact_id: "st1",
      proposal_id: "p1",
      status: "rejected" as const,
      changes: [{ key: "assistant.answer_depth", label: "回答深度", before: "standard", after: "deep" }],
    };
    const { container: stContainer } = render(<SettingsChangeCard artifact={settingsArt} busy={false} onResolve={vi.fn()} />);
    expect(stContainer.querySelector(".hitl-card")?.getAttribute("data-state")).toBe("rejected");
    expect(stContainer.querySelector(".hitl-status-pill")?.textContent).toBe("已取消修改");
  });
});
