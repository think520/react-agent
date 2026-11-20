import { useRef, type CompositionEventHandler, type KeyboardEventHandler } from "react";
import { Search, X } from "lucide-react";

export type SearchFieldProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel: string;
  className?: string;
  size?: "sm" | "md";
  clearLabel?: string;
  onKeyDown?: KeyboardEventHandler<HTMLInputElement>;
  onCompositionStart?: CompositionEventHandler<HTMLInputElement>;
  onCompositionEnd?: CompositionEventHandler<HTMLInputElement>;
};

export function SearchField({
  value,
  onChange,
  placeholder,
  ariaLabel,
  className,
  size = "md",
  clearLabel = "清除搜索",
  onKeyDown,
  onCompositionStart,
  onCompositionEnd,
}: SearchFieldProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  function handleClear() {
    onChange("");
    inputRef.current?.focus();
  }

  const classes = ["ui-search", size === "sm" ? "ui-search-sm" : "", className ?? ""].filter(Boolean).join(" ");

  return (
    <label className={classes}>
      <Search className="ui-search-icon" size={size === "sm" ? 14 : 15} aria-hidden="true" />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        onCompositionStart={onCompositionStart}
        onCompositionEnd={onCompositionEnd}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
      {value.length > 0 && (
        <button
          type="button"
          className="ui-search-clear"
          aria-label={clearLabel}
          onClick={handleClear}
        >
          <X size={13} aria-hidden="true" />
        </button>
      )}
    </label>
  );
}
