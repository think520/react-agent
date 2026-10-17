import { RefreshCw } from "lucide-react";

import type { ProviderModel } from "../../../types";
import type { ProviderForm } from "./providerForm";

/** 供应商编辑字段（2026-10-17 S3）：名称/地址/密钥/模型列表。 */
export function ProviderFormFields({ form, setForm, working, keyless, onFetchModels, modelInput, setModelInput, onAddModel, onRemoveModel }: {
  form: ProviderForm;
  setForm: (next: ProviderForm) => void;
  working: boolean;
  keyless: boolean;
  onFetchModels: () => void;
  modelInput: { id: string; name: string };
  setModelInput: (next: { id: string; name: string }) => void;
  onAddModel: () => void;
  onRemoveModel: (id: string) => void;
}) {
  return <>
    <label className="settings-field"><span>名称</span><input value={form.name} maxLength={80} disabled={working} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
    <label className="settings-field"><span>API 地址（base_url）</span><input value={form.base_url} maxLength={300} disabled={working} onChange={(event) => setForm({ ...form, base_url: event.target.value })} /></label>
    <label className="settings-field"><span>API Key{keyless ? "（本地服务可留空）" : ""}</span><input type="password" value={form.api_key} disabled={working} autoComplete="off" placeholder={keyless ? "本地服务无需填写" : "留空 = 不修改已有密钥"} onChange={(event) => setForm({ ...form, api_key: event.target.value })} /></label>

    <div className="settings-model-head">
      <span>模型列表{form.models.length ? " · " + form.models.length + " 个" : ""}</span>
      <button className="quiet-button" type="button" disabled={working || !form.base_url.trim()} onClick={onFetchModels}><RefreshCw size={13} />读取模型</button>
    </div>
    <p className="settings-model-hint">从「读取模型」拉取，或手动输入。默认模型用于该供应商的常规调用。</p>
    <div className="settings-model-list">
      {form.models.map((model: ProviderModel) => (
        <div className="settings-model-row" key={model.id}>
          <span><strong>{model.name || model.id}</strong><small>{model.id}</small></span>
          {form.model_default === model.id && <i>默认</i>}
          <button className="quiet-button" type="button" disabled={working} onClick={() => setForm({ ...form, model_default: model.id })}>设为默认</button>
          <button className="quiet-button danger" type="button" disabled={working || form.models.length <= 1} onClick={() => onRemoveModel(model.id)}>移除</button>
        </div>
      ))}
      {!form.models.length && <p className="settings-empty">还没有模型。先「读取模型」或手动添加。</p>}
    </div>
    <div className="settings-model-add">
      <input value={modelInput.id} disabled={working} maxLength={120} placeholder="模型 ID（如 deepseek-chat）" onChange={(event) => setModelInput({ ...modelInput, id: event.target.value })} />
      <input value={modelInput.name} disabled={working} maxLength={120} placeholder="显示名（可选）" onChange={(event) => setModelInput({ ...modelInput, name: event.target.value })} />
      <button className="quiet-button" type="button" disabled={working || !modelInput.id.trim()} onClick={onAddModel}>添加</button>
    </div>
  </>;
}
