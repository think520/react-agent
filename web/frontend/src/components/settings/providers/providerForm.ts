import type { ProviderModel, ProviderPreset, ProviderSummary } from "../../../types";

/** 供应商编辑表单（2026-10-17 S3：从 ProviderManagerDialog 原样搬出）。 */
export interface ProviderForm {
  name: string;
  base_url: string;
  api_key: string;
  model_default: string;
  models: ProviderModel[];
}

export const emptyForm: ProviderForm = { name: "", base_url: "", api_key: "", model_default: "", models: [] };

export function formFromProvider(provider: ProviderSummary): ProviderForm {
  return {
    name: provider.name,
    base_url: provider.base_url || "",
    api_key: "",
    model_default: provider.model || "",
    models: provider.models?.length ? provider.models : provider.model ? [{ id: provider.model, name: provider.model }] : [],
  };
}

export function formFromPreset(preset?: ProviderPreset): ProviderForm {
  return {
    ...emptyForm,
    name: preset?.name || "",
    base_url: preset?.base_url || "",
    model_default: preset?.model_default || "",
    models: preset?.models?.length ? preset.models : [],
  };
}
