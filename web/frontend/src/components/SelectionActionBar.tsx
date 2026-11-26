import { Quote, X } from "lucide-react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";

import type { SelectionAnchor } from "../hooks/useTextSelection";

export interface SelectionToolbarAction {
  id: string;
  label: string;
  icon?: ReactNode;
  primary?: boolean;
  onClick: () => void;
}

/**
 * Shared floating selection toolbar inspired by beautifului Selection Actions,
 * docked to Bobodan's paper-soft surface and ring tokens.
 */
export function SelectionActionBar({
  quote,
  anchor,
  actions,
  onClose,
}: {
  quote: string;
  anchor: SelectionAnchor | null;
  actions: SelectionToolbarAction[];
  onClose: () => void;
}) {
  if (!quote) return null;

  const style = anchor
    ? {
        left: Math.min(Math.max(anchor.x, 190), Math.max(190, window.innerWidth - 190)),
        top: anchor.placement === "above"
          ? Math.min(Math.max(anchor.y, 64), Math.max(64, window.innerHeight - 56))
          : Math.min(Math.max(anchor.y, 56), Math.max(56, window.innerHeight - 64)),
      }
    : undefined;

  return createPortal(
    <div
      data-selection-toolbar="true"
      role="toolbar"
      aria-label="划词操作"
      className={anchor
        ? `selection-toolbar floating ${anchor.placement === "below" ? "placement-below" : "placement-above"}`
        : "selection-toolbar"}
      style={style}
      onMouseDown={(event) => event.preventDefault()}
    >
      <Quote size={14} aria-hidden="true" />
      <span className="selection-toolbar-count">已选 {quote.length} 字</span>
      <i className="selection-toolbar-sep" aria-hidden="true" />
      <div className="selection-toolbar-actions">
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            className={`selection-action-btn${action.primary ? " is-primary" : ""}`}
            onClick={action.onClick}
          >
            {action.icon}
            <span>{action.label}</span>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="selection-toolbar-close"
        aria-label="取消"
        title="取消（Esc）"
        onClick={onClose}
      >
        <X size={14} />
      </button>
    </div>,
    document.body,
  );
}
