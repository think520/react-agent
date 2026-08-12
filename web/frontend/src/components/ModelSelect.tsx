import type { ProviderSummary } from "../types";
import { DropdownSelect, type DropdownGroup } from "./DropdownSelect";

/** P5G.4：两级模型选择器——「供应商分组 → 模型」。value 格式 `provider::model`。 */
export function ModelSelect({ providers, value, onChange, label, includeDefault, className, bordered }: {
  providers: ProviderSummary[];
  value: string;
  onChange: (value: string) => void;
  label: string;
  includeDefault?: boolean;
  className?: string;
  bordered?: boolean;
}) {
  const groups: DropdownGroup[] = providers
    .filter((item) => item.configured)
    .map((provider) => ({
      label: provider.name,
      options: (provider.models?.length ? provider.models : provider.model ? [{ id: provider.model, name: provider.model }] : [])
        .map((model) => ({ value: `${provider.name}::${model.id}`, label: model.name || model.id })),
    }));

  return (
    <DropdownSelect
      value={value}
      onChange={onChange}
      groups={groups}
      includeDefault={includeDefault}
      defaultLabel="跟随默认模型"
      ariaLabel={label}
      className={`${bordered ? "bordered" : ""} ${className || ""}`}
    />
  );
}
