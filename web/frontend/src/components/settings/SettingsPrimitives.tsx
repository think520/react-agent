/**
 * 设置区设计系统（2026-10-17 S1：对齐 openhanako 的 settings/components 原语）。
 * 只负责结构（Page / Section / Row / Field / Toggle / Segmented / Stack / Inline），
 * 视觉全部走 Bobodan 现有令牌与类名，不新增色板。
 */
import type { ReactNode } from "react";

export function SettingsPage({ tab, children }: { tab: string; children: ReactNode }) {
  return <div className="settings-page" data-settings-page={tab}>{children}</div>;
}

export function SettingsHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <div className="settings-page-heading"><span>{eyebrow}</span><h2>{title}</h2></div>;
}

export function SettingsSection({ title, description, footer, children }: {
  title: string;
  description?: string;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return <section className="settings-section">
    <header className="settings-section-head">
      <div><h3>{title}</h3>{description && <p>{description}</p>}</div>
    </header>
    <div className="settings-section-body">{children}</div>
    {footer && <footer className="settings-section-footer">{footer}</footer>}
  </section>;
}

export function SettingsStack({ children }: { children: ReactNode }) {
  return <div className="settings-stack">{children}</div>;
}

export function SettingsRow({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <div className="setting-row"><span><strong>{label}</strong>{hint && <small>{hint}</small>}</span><div>{children}</div></div>;
}

export function SettingsField({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="settings-field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}

export function SettingsToggle({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return <button type="button" className={`setting-toggle ${checked ? "on" : ""}`} role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}><i /></button>;
}

export function SettingsSegmented<T extends string | number>({ value, options, onChange, label }: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  label: string;
}) {
  return <div className="setting-segmented" role="radiogroup" aria-label={label}>{options.map((option) => <button type="button" role="radio" aria-checked={option.value === value} className={option.value === value ? "active" : ""} key={String(option.value)} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>;
}

export function SettingsFooter({ children }: { children: ReactNode }) {
  return <footer className="settings-section-footer">{children}</footer>;
}
