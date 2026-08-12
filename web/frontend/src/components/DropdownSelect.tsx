import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";

export interface DropdownOption {
  value: string;
  label: string;
  disabled?: boolean;
  hint?: string;
}

export interface DropdownGroup {
  label: string;
  options: DropdownOption[];
}

/** 主题化下拉：替代原生 select，面板跟随暖纸色设计语言。 */
export function DropdownSelect({
  value,
  onChange,
  options,
  groups,
  includeDefault = false,
  defaultLabel = "跟随默认模型",
  ariaLabel,
  disabled = false,
  className = "",
  triggerClassName = "",
  placeholder = "请选择",
}: {
  value: string;
  onChange: (value: string) => void;
  options?: DropdownOption[];
  groups?: DropdownGroup[];
  includeDefault?: boolean;
  defaultLabel?: string;
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelPos, setPanelPos] = useState({ top: 0, left: 0, minWidth: 0, up: false });

  const flatOptions = useMemo<DropdownOption[]>(() => {
    const list: DropdownOption[] = [];
    if (includeDefault) list.push({ value: "default", label: defaultLabel });
    if (groups) {
      for (const group of groups) list.push(...group.options);
    } else if (options) {
      list.push(...options);
    }
    return list;
  }, [includeDefault, defaultLabel, groups, options]);

  const currentLabel = useMemo(() => {
    if (includeDefault && value === "default") return defaultLabel;
    const found = flatOptions.find((option) => option.value === value);
    return found?.label || placeholder;
  }, [value, flatOptions, includeDefault, defaultLabel, placeholder]);

  function toggle() {
    if (disabled) return;
    if (!open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const panelHeight = Math.min(320, flatOptions.length * 34 + 16);
      const spaceBelow = window.innerHeight - rect.bottom;
      const up = spaceBelow < panelHeight + 8 && rect.top > spaceBelow;
      setPanelPos({ top: rect.bottom, left: rect.left, minWidth: Math.max(rect.width, 160), up });
      setActiveIndex(-1);
    }
    setOpen((current) => !current);
  }

  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onScroll() { setOpen(false); }
    document.addEventListener("mousedown", onDown);
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  function select(value: string) {
    onChange(value);
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) { toggle(); return; }
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((current) => {
        const next = (current + delta + flatOptions.length) % flatOptions.length;
        return next;
      });
    } else if (event.key === "Enter" || event.key === " ") {
      if (open && activeIndex >= 0) {
        event.preventDefault();
        const option = flatOptions[activeIndex];
        if (option && !option.disabled) select(option.value);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const panelStyle: React.CSSProperties = {
    position: "fixed",
    left: panelPos.left,
    minWidth: panelPos.minWidth,
    maxWidth: 340,
  };
  if (panelPos.up) {
    panelStyle.bottom = window.innerHeight - (panelPos.top - 8);
  } else {
    panelStyle.top = panelPos.top + 4;
  }

  const panel = open && createPortal(
    <div ref={panelRef} className="dropdown-panel" role="listbox" aria-label={ariaLabel} style={panelStyle}>
      {includeDefault && <button type="button" role="option" aria-selected={value === "default"} className={`dropdown-item ${value === "default" ? "selected" : ""} ${activeIndex === 0 ? "active" : ""}`} onClick={() => select("default")} onMouseEnter={() => setActiveIndex(0)}><span>{defaultLabel}</span>{value === "default" && <Check size={14} />}</button>}
      {groups ? groups.map((group) => (
        <div className="dropdown-group" key={group.label}>
          <div className="dropdown-group-label">{group.label}</div>
          {group.options.map((option) => {
            const flatIndex = flatOptions.findIndex((item) => item.value === option.value);
            return (
              <button type="button" role="option" aria-selected={option.value === value} key={option.value}
                className={`dropdown-item ${option.value === value ? "selected" : ""} ${flatIndex === activeIndex ? "active" : ""}`}
                disabled={option.disabled}
                onClick={() => !option.disabled && select(option.value)}
                onMouseEnter={() => setActiveIndex(flatIndex)}>
                <span>{option.label}</span>
                {option.hint && <small>{option.hint}</small>}
                {option.value === value && <Check size={14} />}
              </button>
            );
          })}
        </div>
      )) : (
        <>
          {(options || []).map((option, index) => {
            const flatIndex = includeDefault ? index + 1 : index;
            return (
              <button type="button" role="option" aria-selected={option.value === value} key={option.value}
                className={`dropdown-item ${option.value === value ? "selected" : ""} ${flatIndex === activeIndex ? "active" : ""}`}
                disabled={option.disabled}
                onClick={() => !option.disabled && select(option.value)}
                onMouseEnter={() => setActiveIndex(flatIndex)}>
                <span>{option.label}</span>
                {option.hint && <small>{option.hint}</small>}
                {option.value === value && <Check size={14} />}
              </button>
            );
          })}
        </>
      )}
    </div>,
    document.body,
  );

  return (
    <span className={`dropdown-select ${className}`}>
      <button ref={buttonRef} type="button" className={`dropdown-trigger ${triggerClassName}`}
        onClick={toggle} onKeyDown={onKeyDown} disabled={disabled}
        aria-haspopup="listbox" aria-expanded={open} aria-label={ariaLabel} title={ariaLabel}>
        <span className="dropdown-trigger-label">{currentLabel}</span>
        <ChevronDown size={12} className="dropdown-chevron" />
      </button>
      {panel}
    </span>
  );
}
