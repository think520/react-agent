import { ChevronRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { isCursorInSubmenuSafeTriangle, type Point } from "./safeTriangle";

export const SUBMENU_OPEN_DELAY_MS = 100;
export const SUBMENU_CLOSE_DELAY_MS = 180;
export const SAFE_TRIANGLE_IDLE_MS = 260;

export type DesktopMenuItem =
  | { type: "divider"; id: string }
  | {
      type?: "item";
      id: string;
      label: string;
      icon?: ReactNode;
      danger?: boolean;
      disabled?: boolean;
      onSelect?: () => void;
      children?: DesktopMenuItem[];
    };

export interface DesktopMenuProps {
  triggerLabel?: string;
  triggerIcon?: ReactNode;
  triggerClassName?: string;
  className?: string;
  ariaLabel?: string;
  align?: "left" | "right";
  compactTrigger?: boolean;
  items: DesktopMenuItem[];
  onOpenChange?: (open: boolean) => void;
}

type ActionItem = Exclude<DesktopMenuItem, { type: "divider" }>;

function isActionItem(item: DesktopMenuItem): item is ActionItem {
  return item.type !== "divider";
}

/**
 * 桌面端多级菜单原语：
 * - 点击空白、按 Esc 关闭并归还焦点；
 * - 子菜单支持开启延时（100ms）、关闭延时（180ms）与指针安全三角区（Safe Triangle）。
 */
export function DesktopMenu({
  triggerLabel,
  triggerIcon,
  triggerClassName = "",
  className = "",
  ariaLabel,
  align = "right",
  compactTrigger = false,
  items,
  onOpenChange,
}: DesktopMenuProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [openSubmenuId, setOpenSubmenuId] = useState<string | null>(null);
  const [subActiveIndex, setSubActiveIndex] = useState(-1);
  const [panelPos, setPanelPos] = useState<{ top: number; left: number; minWidth: number; up: boolean; bottom: number }>({
    top: 0,
    left: 0,
    minWidth: 168,
    up: false,
    bottom: 0,
  });
  const [submenuPos, setSubmenuPos] = useState<{ top: number; left: number; side: "right" | "left" }>({
    top: 0,
    left: 0,
    side: "right",
  });

  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const submenuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const submenuItemRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const openTimerRef = useRef<number | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const triangleIdleTimerRef = useRef<number | null>(null);
  const submenuAnchorRef = useRef<Point | null>(null);
  const openSubmenuIdRef = useRef<string | null>(null);
  openSubmenuIdRef.current = openSubmenuId;

  const actionItems = useMemo(() => items.filter(isActionItem), [items]);
  const openSubmenuParent = useMemo(
    () => actionItems.find((item) => item.id === openSubmenuId && Boolean(item.children?.length)) ?? null,
    [actionItems, openSubmenuId],
  );
  const submenuActionItems = useMemo(
    () => (openSubmenuParent?.children || []).filter(isActionItem),
    [openSubmenuParent],
  );

  const clearHoverTimers = useCallback(() => {
    if (openTimerRef.current !== null) {
      window.clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    if (triangleIdleTimerRef.current !== null) {
      window.clearTimeout(triangleIdleTimerRef.current);
      triangleIdleTimerRef.current = null;
    }
  }, []);

  const setMenuOpen = useCallback(
    (next: boolean, restoreFocus = false) => {
      clearHoverTimers();
      setOpen(next);
      onOpenChange?.(next);
      if (!next) {
        setOpenSubmenuId(null);
        setActiveIndex(-1);
        setSubActiveIndex(-1);
        submenuAnchorRef.current = null;
        if (restoreFocus) {
          window.requestAnimationFrame(() => triggerRef.current?.focus());
        }
      }
    },
    [clearHoverTimers, onOpenChange],
  );

  const computeSubmenuPosition = useCallback((parentId: string) => {
    const parentBtn = itemRefs.current[parentId];
    const mainRect = panelRef.current?.getBoundingClientRect();
    const rowRect = parentBtn?.getBoundingClientRect() ?? mainRect;
    if (!rowRect || !mainRect) return;
    const estWidth = 196;
    const childCount = actionItems.find((item) => item.id === parentId)?.children?.length ?? 6;
    const maxAllowedHeight = Math.max(140, window.innerHeight - 24);
    const estHeight = Math.min(280, Math.max(48, childCount * 36 + 12), maxAllowedHeight);
    const canRight = mainRect.right + 4 + estWidth <= window.innerWidth - 12;
    const side: "right" | "left" = canRight ? "right" : "left";
    const left = side === "right" ? mainRect.right + 4 : Math.max(12, mainRect.left - estWidth - 4);
    const top = Math.max(12, Math.min(rowRect.top - 4, window.innerHeight - estHeight - 12));
    setSubmenuPos({ top, left, side });
  }, [actionItems]);

  const activateSubmenuNow = useCallback(
    (id: string | null) => {
      setOpenSubmenuId(id);
      setSubActiveIndex(-1);
      if (id) computeSubmenuPosition(id);
    },
    [computeSubmenuPosition],
  );

  const toggleMenu = useCallback(() => {
    if (!open && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      const panelWidth = 196;
      const panelHeight = Math.min(340, items.length * 36 + 16);
      const spaceBelow = window.innerHeight - rect.bottom;
      const up = spaceBelow < panelHeight + 8 && rect.top > spaceBelow;
      const preferredLeft = align === "right" ? rect.right - panelWidth : rect.left;
      const left = Math.max(12, Math.min(preferredLeft, window.innerWidth - panelWidth - 12));
      setPanelPos({
        top: rect.bottom + 6,
        bottom: window.innerHeight - rect.top + 6,
        left,
        minWidth: Math.max(168, rect.width),
        up,
      });
      setMenuOpen(true);
    } else {
      setMenuOpen(false);
    }
  }, [align, items.length, open, setMenuOpen]);

  useEffect(() => clearHoverTimers, [clearHoverTimers]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent | PointerEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      if (submenuRef.current?.contains(target)) return;
      setMenuOpen(false);
    }
    function onKeyDownGlobal(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false, true);
      }
    }
    function onScrollOrResize(event: Event) {
      const target = event.target as Node | null;
      if (target && (panelRef.current?.contains(target) || submenuRef.current?.contains(target))) return;
      setMenuOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDownGlobal);
    window.addEventListener("resize", onScrollOrResize);
    window.addEventListener("scroll", onScrollOrResize, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDownGlobal);
      window.removeEventListener("resize", onScrollOrResize);
      window.removeEventListener("scroll", onScrollOrResize, true);
    };
  }, [open, setMenuOpen]);

  const scheduleHoverTarget = useCallback(
    (item: ActionItem, cursor: Point) => {
      const hasSubmenu = Boolean(item.children?.length && !item.disabled);
      const currentOpenId = openSubmenuIdRef.current;

      if (currentOpenId && currentOpenId !== item.id) {
        const subRect = submenuRef.current?.getBoundingClientRect() ?? null;
        if (isCursorInSubmenuSafeTriangle(cursor, submenuAnchorRef.current, subRect, submenuPos.side)) {
          if (triangleIdleTimerRef.current !== null) window.clearTimeout(triangleIdleTimerRef.current);
          triangleIdleTimerRef.current = window.setTimeout(() => {
            submenuAnchorRef.current = cursor;
            if (hasSubmenu) activateSubmenuNow(item.id);
            else activateSubmenuNow(null);
          }, SAFE_TRIANGLE_IDLE_MS);
          return;
        }
      }

      clearHoverTimers();

      if (hasSubmenu) {
        if (currentOpenId === item.id) {
          submenuAnchorRef.current = cursor;
          return;
        }
        openTimerRef.current = window.setTimeout(() => {
          submenuAnchorRef.current = cursor;
          activateSubmenuNow(item.id);
        }, SUBMENU_OPEN_DELAY_MS);
      } else if (currentOpenId) {
        closeTimerRef.current = window.setTimeout(() => {
          activateSubmenuNow(null);
        }, SUBMENU_CLOSE_DELAY_MS);
      }
    },
    [activateSubmenuNow, clearHoverTimers, submenuPos.side],
  );

  function handleParentMouseMove(event: ReactMouseEvent<HTMLDivElement>) {
    if (!openSubmenuIdRef.current) {
      submenuAnchorRef.current = { x: event.clientX, y: event.clientY };
    }
  }

  function handleSubmenuEnter() {
    clearHoverTimers();
  }

  function handleSubmenuLeave() {
    if (!openSubmenuIdRef.current) return;
    if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
    closeTimerRef.current = window.setTimeout(() => {
      activateSubmenuNow(null);
    }, SUBMENU_CLOSE_DELAY_MS);
  }

  function selectAction(item: ActionItem) {
    if (item.disabled) return;
    if (item.children?.length) {
      activateSubmenuNow(openSubmenuId === item.id ? null : item.id);
      return;
    }
    item.onSelect?.();
    setMenuOpen(false);
  }

  function handleMenuKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (openSubmenuParent && submenuActionItems.length > 0 && subActiveIndex >= 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSubActiveIndex((cur) => (cur + 1) % submenuActionItems.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSubActiveIndex((cur) => (cur - 1 + submenuActionItems.length) % submenuActionItems.length);
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        activateSubmenuNow(null);
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        const chosen = submenuActionItems[subActiveIndex];
        if (chosen) selectAction(chosen);
        return;
      }
    }

    if (!actionItems.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((cur) => (cur + 1) % actionItems.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((cur) => (cur - 1 + actionItems.length) % actionItems.length);
    } else if (event.key === "ArrowRight") {
      const current = actionItems[activeIndex];
      if (current?.children?.length && !current.disabled) {
        event.preventDefault();
        activateSubmenuNow(current.id);
        setSubActiveIndex(0);
      }
    } else if (event.key === "Enter" || event.key === " ") {
      const current = actionItems[activeIndex];
      if (current) {
        event.preventDefault();
        selectAction(current);
      }
    }
  }

  const panelStyle: React.CSSProperties = {
    position: "fixed",
    left: panelPos.left,
    minWidth: panelPos.minWidth,
    ...(panelPos.up ? { bottom: panelPos.bottom } : { top: panelPos.top }),
  };

  const triggerClasses = [
    "desktop-menu-trigger",
    compactTrigger ? "desktop-menu-trigger-compact" : "",
    triggerClassName,
  ]
    .filter(Boolean)
    .join(" ");

  const portal = open
    ? createPortal(
        <>
          <div
            ref={panelRef}
            className="desktop-menu-panel"
            role="menu"
            aria-label={ariaLabel || triggerLabel || "菜单"}
            style={panelStyle}
            onMouseMove={handleParentMouseMove}
            onKeyDown={handleMenuKeyDown}
          >
            {items.map((entry) => {
              if (!isActionItem(entry)) {
                return <div key={entry.id} className="desktop-menu-divider" role="separator" />;
              }
              const idx = actionItems.findIndex((item) => item.id === entry.id);
              const isSubmenuOpen = openSubmenuId === entry.id;
              return (
                <button
                  key={entry.id}
                  ref={(node) => {
                    itemRefs.current[entry.id] = node;
                  }}
                  type="button"
                  role="menuitem"
                  aria-haspopup={entry.children?.length ? "menu" : undefined}
                  aria-expanded={entry.children?.length ? isSubmenuOpen : undefined}
                  disabled={entry.disabled}
                  className={[
                    "desktop-menu-item",
                    entry.danger ? "danger" : "",
                    idx === activeIndex || isSubmenuOpen ? "active" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onMouseEnter={(event) => {
                    setActiveIndex(idx);
                    scheduleHoverTarget(entry, { x: event.clientX, y: event.clientY });
                  }}
                  onMouseMove={(event) => {
                    if (openSubmenuIdRef.current === entry.id) {
                      submenuAnchorRef.current = { x: event.clientX, y: event.clientY };
                    } else if (openSubmenuIdRef.current && openSubmenuIdRef.current !== entry.id) {
                      scheduleHoverTarget(entry, { x: event.clientX, y: event.clientY });
                    }
                  }}
                  onClick={() => selectAction(entry)}
                >
                  {entry.icon && <span className="desktop-menu-item-icon">{entry.icon}</span>}
                  <span>{entry.label}</span>
                  {entry.children?.length ? <ChevronRight size={16} className="desktop-menu-chevron" aria-hidden="true" /> : null}
                </button>
              );
            })}
          </div>
          {openSubmenuParent && (
            <div
              ref={submenuRef}
              className="desktop-menu-panel desktop-menu-submenu"
              role="menu"
              aria-label={openSubmenuParent.label}
              style={{ position: "fixed", top: submenuPos.top, left: submenuPos.left }}
              onMouseEnter={handleSubmenuEnter}
              onMouseLeave={handleSubmenuLeave}
              onKeyDown={handleMenuKeyDown}
            >
              {(openSubmenuParent.children || []).map((child) => {
                if (!isActionItem(child)) {
                  return <div key={child.id} className="desktop-menu-divider" role="separator" />;
                }
                const subIdx = submenuActionItems.findIndex((item) => item.id === child.id);
                return (
                  <button
                    key={child.id}
                    ref={(node) => {
                      submenuItemRefs.current[child.id] = node;
                    }}
                    type="button"
                    role="menuitem"
                    disabled={child.disabled}
                    className={[
                      "desktop-menu-item",
                      child.danger ? "danger" : "",
                      subIdx === subActiveIndex ? "active" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onMouseEnter={() => setSubActiveIndex(subIdx)}
                    onClick={() => selectAction(child)}
                  >
                    {child.icon && <span className="desktop-menu-item-icon">{child.icon}</span>}
                    <span>{child.label}</span>
                  </button>
                );
              })}
            </div>
          )}
        </>,
        document.body,
      )
    : null;

  return (
    <div className={`desktop-menu ${open ? "is-open" : ""} ${className}`.trim()}>
      <button
        ref={triggerRef}
        type="button"
        className={triggerClasses}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={ariaLabel || triggerLabel}
        onClick={toggleMenu}
      >
        {triggerIcon}
        {triggerLabel && <span>{triggerLabel}</span>}
      </button>
      {portal}
    </div>
  );
}
