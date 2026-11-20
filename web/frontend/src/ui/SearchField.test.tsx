import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { SearchField } from "./SearchField";

afterEach(cleanup);

describe("SearchField", () => {
  it("renders accessible input, updates value, and reveals clear button only when non-empty", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <SearchField value="" onChange={onChange} placeholder="搜索资料" ariaLabel="搜索资料" />,
    );

    const input = screen.getByLabelText("搜索资料") as HTMLInputElement;
    expect(input.placeholder).toBe("搜索资料");
    expect(screen.queryByRole("button", { name: "清除搜索" })).toBeNull();

    fireEvent.change(input, { target: { value: "矩阵" } });
    expect(onChange).toHaveBeenCalledWith("矩阵");

    rerender(
      <SearchField value="矩阵" onChange={onChange} placeholder="搜索资料" ariaLabel="搜索资料" clearLabel="清空搜索" />,
    );

    const clearButton = screen.getByRole("button", { name: "清空搜索" });
    fireEvent.click(clearButton);
    expect(onChange).toHaveBeenLastCalledWith("");
    expect(document.activeElement).toBe(input);
  });

  it("supports size='sm', custom className, and forwards keyboard/IME handlers", () => {
    const onKeyDown = vi.fn();
    const { container } = render(
      <SearchField
        value="设置"
        onChange={() => {}}
        ariaLabel="搜索设置"
        className="settings-search"
        size="sm"
        onKeyDown={onKeyDown}
      />,
    );

    const label = container.querySelector("label");
    expect(label?.className).toContain("ui-search");
    expect(label?.className).toContain("ui-search-sm");
    expect(label?.className).toContain("settings-search");

    fireEvent.keyDown(screen.getByLabelText("搜索设置"), { key: "Enter" });
    expect(onKeyDown).toHaveBeenCalledTimes(1);
  });
});
