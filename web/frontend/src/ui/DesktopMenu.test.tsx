import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DesktopMenu, SAFE_TRIANGLE_IDLE_MS, SUBMENU_CLOSE_DELAY_MS, SUBMENU_OPEN_DELAY_MS } from "./DesktopMenu";
import { isCursorInSubmenuSafeTriangle, isPointInTriangle } from "./safeTriangle";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("safeTriangle geometry", () => {
  it("detects points inside vs outside a triangle and handles degenerate cases", () => {
    const a = { x: 0, y: 50 };
    const b = { x: 100, y: 0 };
    const c = { x: 100, y: 100 };

    expect(isPointInTriangle({ x: 50, y: 50 }, a, b, c)).toBe(true);
    expect(isPointInTriangle({ x: 50, y: 90 }, a, b, c)).toBe(false);
    expect(isPointInTriangle({ x: 10, y: 10 }, { x: 0, y: 0 }, { x: 50, y: 0 }, { x: 100, y: 0 })).toBe(false);
  });

  it("checks diagonal pointer movement toward right and left submenus", () => {
    const rightRect = { left: 200, right: 360, top: 80, bottom: 200 };
    const anchor = { x: 150, y: 120 };
    expect(isCursorInSubmenuSafeTriangle({ x: 175, y: 145 }, anchor, rightRect, "right")).toBe(true);
    expect(isCursorInSubmenuSafeTriangle({ x: 175, y: 230 }, anchor, rightRect, "right")).toBe(false);
    expect(isCursorInSubmenuSafeTriangle({ x: 140, y: 120 }, anchor, rightRect, "right")).toBe(false);

    const leftRect = { left: 20, right: 180, top: 80, bottom: 200 };
    const leftAnchor = { x: 220, y: 120 };
    expect(isCursorInSubmenuSafeTriangle({ x: 200, y: 150 }, leftAnchor, leftRect, "left")).toBe(true);
    expect(isCursorInSubmenuSafeTriangle({ x: 230, y: 150 }, leftAnchor, leftRect, "left")).toBe(false);
  });
});

describe("DesktopMenu", () => {
  it("opens, closes on outside pointerdown or Escape, and runs selected action", () => {
    const onRename = vi.fn();
    render(
      <div>
        <div data-testid="outside">outside</div>
        <DesktopMenu
          triggerLabel="更多"
          items={[
            { id: "rename", label: "重命名", onSelect: onRename },
            { id: "archive", label: "归档", onSelect: vi.fn() },
          ]}
        />
      </div>,
    );

    const trigger = screen.getByRole("button", { name: "更多" });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu", { name: "更多" })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();

    fireEvent.click(trigger);
    fireEvent.pointerDown(screen.getByTestId("outside"));
    expect(screen.queryByRole("menu")).toBeNull();

    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: "重命名" }));
    expect(onRename).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("applies open/close delays and safe triangle protection for submenus", () => {
    vi.useFakeTimers();
    const onMove = vi.fn();

    render(
      <DesktopMenu
        triggerLabel="操作"
        items={[
          {
            id: "move",
            label: "移动到",
            children: [{ id: "root", label: "资料库根目录", onSelect: onMove }],
          },
          { id: "archive", label: "归档", onSelect: vi.fn() },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "操作" }));
    const parentMenu = screen.getByRole("menu", { name: "操作" });
    vi.spyOn(parentMenu, "getBoundingClientRect").mockReturnValue({
      left: 40,
      right: 200,
      top: 60,
      bottom: 140,
      width: 160,
      height: 80,
      x: 40,
      y: 60,
      toJSON: () => ({}),
    });

    const moveItem = screen.getByRole("menuitem", { name: "移动到" });
    const archiveItem = screen.getByRole("menuitem", { name: "归档" });

    // Open delay: not open before 100ms, open after 100ms.
    fireEvent.mouseEnter(moveItem, { clientX: 120, clientY: 80 });
    expect(screen.queryByRole("menu", { name: "移动到" })).toBeNull();
    act(() => {
      vi.advanceTimersByTime(SUBMENU_OPEN_DELAY_MS);
    });
    const submenu = screen.getByRole("menu", { name: "移动到" });
    vi.spyOn(submenu, "getBoundingClientRect").mockReturnValue({
      left: 204,
      right: 360,
      top: 60,
      bottom: 160,
      width: 156,
      height: 100,
      x: 204,
      y: 60,
      toJSON: () => ({}),
    });

    // Diagonal move through Safe Triangle keeps submenu open past close delay.
    fireEvent.mouseMove(archiveItem, { clientX: 160, clientY: 110 });
    act(() => {
      vi.advanceTimersByTime(SUBMENU_CLOSE_DELAY_MS + 10);
    });
    expect(screen.getByRole("menu", { name: "移动到" })).toBeInTheDocument();

    // Resting idle past SAFE_TRIANGLE_IDLE_MS switches and closes submenu.
    act(() => {
      vi.advanceTimersByTime(SAFE_TRIANGLE_IDLE_MS);
    });
    expect(screen.queryByRole("menu", { name: "移动到" })).toBeNull();
  });
});
