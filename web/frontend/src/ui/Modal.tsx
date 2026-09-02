import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Shared modal foundation: one backdrop recipe, one 220ms entrance, Escape
 * handled through a stacking discipline so nested dialogs (provider manager
 * inside settings, memory manager on top of either) close one layer per press,
 * plus a basic focus trap. Visual styling lives under .ui-modal-* in
 * styles.css; components keep their own panel markup inside children.
 */

type StackToken = object;

// Module-level stack of currently open modals; only the topmost may react
// to Escape or be dismissed by clicks.
const modalStack: StackToken[] = [];

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({
  onClose,
  children,
  ariaLabel,
  labelledBy,
  className = "",
  backdropClassName = "",
  zIndex,
  dismissible = true,
}: {
  onClose: () => void;
  children: ReactNode;
  ariaLabel?: string;
  labelledBy?: string;
  className?: string;
  /** Extra class for special layouts (e.g. bottom sheets) on the backdrop. */
  backdropClassName?: string;
  zIndex?: number;
  /** Backdrop click and Escape honor this; forced flows set false. */
  dismissible?: boolean;
}) {
  const panelRef = useRef<HTMLElement>(null);
  // onClose passed from parents changes identity across renders; keep the
  // keyboard handler stable without rebinding the whole stack bookkeeping.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);
  const tokenRef = useRef<StackToken>({});

  const requestClose = useCallback(() => {
    if (!dismissible) return;
    onCloseRef.current();
  }, [dismissible]);

  useEffect(() => {
    const token = tokenRef.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    modalStack.push(token);
    document.body.classList.add("ui-modal-open");
    panelRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && modalStack[modalStack.length - 1] === token) {
        event.stopPropagation();
        requestClose();
        return;
      }
      if (event.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => element.offsetParent !== null || element === document.activeElement,
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      const index = modalStack.indexOf(token);
      if (index >= 0) modalStack.splice(index, 1);
      if (!modalStack.length) document.body.classList.remove("ui-modal-open");
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [requestClose]);

  return (
    <div
      className={`ui-modal-backdrop ${backdropClassName}`}
      role="presentation"
      style={zIndex ? { zIndex } : undefined}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <section
        ref={panelRef}
        className={`ui-modal-panel ${className}`}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={labelledBy}
        tabIndex={-1}
      >
        {children}
      </section>
    </div>
  );
}

/** Confirmation dialog shared by destructive flows (replaces window.confirm). */
export function ConfirmDialog({
  title,
  detail,
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  detail?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal onClose={onCancel} ariaLabel={title} zIndex={210}>
      <div className="ui-confirm">
        <h3>{title}</h3>
        {detail && <div className="ui-confirm-detail">{detail}</div>}
        <footer>
          <button className="quiet-button" onClick={onCancel} disabled={busy}>{cancelLabel}</button>
          <button className={danger ? "danger-button" : "primary-button"} onClick={onConfirm} disabled={busy}>
            {busy ? "正在处理…" : confirmLabel}
          </button>
        </footer>
      </div>
    </Modal>
  );
}

export interface ConfirmOptions {
  title: string;
  detail?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

/**
 * Promise-flavored window.confirm replacement:
 *   const { confirm, confirmElement } = useConfirm();
 *   if (!(await confirm({ title: "删除？" }))) return;
 * Render {confirmElement} anywhere in the component's output.
 */
export function useConfirm() {
  const [pending, setPending] = useState<{
    options: ConfirmOptions;
    resolve: (value: boolean) => void;
    busy: boolean;
  } | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setPending({ options, resolve, busy: false })),
    [],
  );

  // If the owning component unmounts with a confirm still open, settle the
  // promise as cancelled instead of leaving the awaiting flow hanging.
  useEffect(() => () => {
    setPending((current) => {
      current?.resolve(false);
      return null;
    });
  }, []);

  const element = pending ? (
    <ConfirmDialog
      {...pending.options}
      busy={pending.busy}
      onCancel={() => {
        pending.resolve(false);
        setPending(null);
      }}
      onConfirm={() => {
        pending.resolve(true);
        setPending(null);
      }}
    />
  ) : null;

  return { confirm, confirmElement: element };
}
