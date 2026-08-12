import type { ProviderSummary } from "../types";

/** P5G.4：两级模型选择器——「供应商分组 → 模型」。value 格式 `provider::model`。 */
export function ModelSelect({ providers, value, onChange, label, includeDefault, className }: {
  providers: ProviderSummary[];
  value: string;
  onChange: (value: string) => void;
  label: string;
  includeDefault?: boolean;
  className?: string;
}) {
  const configured = providers.filter((item) => item.configured);
  return (
    <select
      className={className || "settings-inline-select"}
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {includeDefault && <option value="default">跟随默认模型</option>}
      {configured.map((provider) => (
        <optgroup key={provider.name} label={provider.name}>
          {(provider.models?.length ? provider.models : provider.model ? [{ id: provider.model, name: provider.model }] : []).map((model) => (
            <option key={`${provider.name}::${model.id}`} value={`${provider.name}::${model.id}`}>{model.name || model.id}</option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
