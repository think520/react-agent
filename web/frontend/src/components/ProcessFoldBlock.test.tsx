import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ProcessFoldBlock } from "./ProcessFoldBlock";

afterEach(cleanup);

describe("ProcessFoldBlock", () => {
  it("renders compact tool-step chips when step count is below fold threshold", () => {
    render(
      <ProcessFoldBlock
        steps={[
          { phase: "search", message: "资料检索", elapsed: 0.4 },
          { phase: "graph", message: "知识地图", elapsed: 0.2 },
        ]}
      />,
    );

    expect(screen.getByText("资料检索")).toBeInTheDocument();
    expect(screen.getByText("0.4s")).toBeInTheDocument();
    expect(screen.getByText("知识地图")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("toggles smooth accordion state via aria-expanded and data-open when folded", () => {
    const { container } = render(
      <ProcessFoldBlock
        steps={[
          { phase: "s1", message: "定位目录", elapsed: 0.1 },
          { phase: "s2", message: "检索文档", elapsed: 0.3 },
          { phase: "s3", message: "核对引用", elapsed: 0.2 },
        ]}
      />,
    );

    const root = container.querySelector(".process-fold-collapsed");
    const trigger = screen.getByRole("button", { name: /共 3 个步骤/ });
    expect(root?.getAttribute("data-open")).toBe("false");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(trigger);
    expect(root?.getAttribute("data-open")).toBe("true");
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
  });
});
