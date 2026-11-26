import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SelectionActionBar } from "./SelectionActionBar";
import { ChatTranscript } from "./chat/ChatTranscript";

afterEach(() => {
  cleanup();
  window.getSelection()?.removeAllRanges();
});

describe("SelectionActionBar", () => {
  it("renders floating portal actions, preserves selection on mousedown, and triggers action + close", () => {
    const onExplain = vi.fn();
    const onClose = vi.fn();
    render(
      <SelectionActionBar
        quote="贪心选择性质"
        anchor={{ x: 240, y: 120, placement: "above" }}
        actions={[
          { id: "explain", label: "解释这段", primary: true, onClick: onExplain },
        ]}
        onClose={onClose}
      />,
    );

    const toolbar = screen.getByRole("toolbar", { name: "划词操作" });
    expect(toolbar.className).toContain("placement-above");
    expect(screen.getByText("已选 6 字")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "解释这段" }));
    expect(onExplain).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows selection action bar when selecting text inside completed ChatTranscript answer", () => {
    const onExplain = vi.fn();
    const onQuote = vi.fn();
    const { container } = render(
      <MemoryRouter>
        <ChatTranscript
          messages={[
            { role: "user", content: "什么是贪心算法？" },
            { role: "assistant", content: "每一步都选当前局部最优解，并用交换论证说明可行性。" },
          ]}
          status={null}
          brandState="ready"
          assistantName="Bobodan"
          sending={false}
          error=""
          truncated={null}
          onContinue={() => undefined}
          onPreparePractice={() => undefined}
          onSelectionExplain={onExplain}
          onSelectionQuote={onQuote}
          onRetry={() => undefined}
          renderArtifact={() => null}
          onOpenReference={() => undefined}
          onOpenSources={() => undefined}
        />
      </MemoryRouter>,
    );

    const prose = container.querySelector('[data-selectable-answer="true"] p')!;
    const textNode = prose.firstChild!;
    const range = document.createRange();
    range.setStart(textNode, 0);
    range.setEnd(textNode, 8);
    (prose as HTMLElement).getBoundingClientRect = () => ({ left: 100, right: 220, top: 140, bottom: 160, width: 120, height: 20, x: 100, y: 140, toJSON: () => ({}) });

    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);

    fireEvent.mouseUp(container.querySelector(".conversation")!);
    expect(screen.getByRole("toolbar", { name: "划词操作" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "解释这段" }));
    expect(onExplain).toHaveBeenCalledWith("每一步都选当前局");
    expect(screen.queryByRole("toolbar", { name: "划词操作" })).toBeNull();
  });
});
