import { RefreshCw } from "lucide-react";

import type { ModelKind, ProviderModel } from "../../../types";
import { classifyModelKind, modelKindLabel, nextModelKind, resolveModelKind } from "./modelKind";
import type { ProviderForm } from "./providerForm";

/** 供应商编辑字段（2026-10-17 S3）：名称/地址/密钥/模型列表（带能力标签防呆）。 */
export function ProviderFormFields({ form, setForm, working, keyless, onFetchModels, modelInput, setModelInput, onAddModel, onRemoveModel }: {
  form: ProviderForm;
  setForm: (next: ProviderForm) => void;
  working: boolean;
  keyless: boolean;
  onFetchModels: () => void;
  modelInput: { id: string; name: string; kind?: ModelKind };
  setModelInput: (next: { id: string; name: string; kind?: ModelKind }) => void;
  onAddModel: () => void;
  onRemoveModel: (id: string) => void;
}) {
  function toggleKind(model: ProviderModel) {
    const updatedKind = nextModelKind(resolveModelKind(model));
    const models = form.models.map((item) => (
      item.id === model.id
        ? { ...item, kind: updatedKind }
        : item
    ));
    let modelDefault = form.model_default;
    if (updatedKind !== "chat" && modelDefault === model.id) {
      modelDefault = models.find((item) => resolveModelKind(item) === "chat")?.id || "";
    }
    setForm({ ...form, models, model_default: modelDefault });
  }

  const pendingKind = modelInput.kind || classifyModelKind(modelInput.id);

  return <>
    <label className="settings-field"><span>名称</span><input value={form.name} maxLength={80} disabled={working} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
    <label className="settings-field"><span>API 地址（base_url）</span><input value={form.base_url} maxLength={300} disabled={working} onChange={(event) => setForm({ ...form, base_url: event.target.value })} /></label>
    <label className="settings-field"><span>API Key{keyless ? "（本地服务可留空）" : ""}</span><input type="password" value={form.api_key} disabled={working} autoComplete="off" placeholder={keyless ? "本地服务无需填写" : "留空 = 不修改已有密钥"} onChange={(event) => setForm({ ...form, api_key: event.target.value })} /></label>

    <div className="settings-model-head">
      <span>模型列表{form.models.length ? " · " + form.models.length + " 个" : ""}</span>
      <button className="quiet-button" type="button" disabled={working || !form.base_url.trim()} onClick={onFetchModels}><RefreshCw size={13} />读取模型</button>
    </div>
    <p className="settings-model-hint">API 地址请填写服务根路径（如 https://api.example.com/v1），不要包含 /chat/completions。点击模型类型标签可切换「对话 / 向量 / 重排」，避免把向量模型误设为默认对话模型。</p>
    <div className="settings-model-list">
      {form.models.map((model: ProviderModel) => {
        const kind = resolveModelKind(model);
        return (
          <div className="settings-model-row" key={model.id}>
            <span><strong>{model.name || model.id}</strong><small>{model.id}</small></span>
            <div className="settings-model-actions">
              <button
                type="button"
                className="model-kind-pill"
                data-kind={kind}
                disabled={working}
                title="点击切换模型类型（对话 / 向量 / 重排）"
                onClick={() => toggleKind(model)}
              >
                {modelKindLabel(kind)}
              </button>
              {form.model_default === model.id && <i>默认</i>}
              {kind === "chat" && form.model_default !== model.id && (
                <button className="quiet-button" type="button" disabled={working} onClick={() => setForm({ ...form, model_default: model.id })}>设为默认</button>
              )}
              <button className="quiet-button danger" type="button" disabled={working || form.models.length <= 1} onClick={() => onRemoveModel(model.id)}>移除</button>
            </div>
          </div>
        );
      })}
      {!form.models.length && <p className="settings-empty">还没有模型。先「读取模型」或手动添加。</p>}
    </div>
    <div className="settings-model-add">
      <input value={modelInput.id} disabled={working} maxLength={120} placeholder="模型 ID（如 deepseek-chat 或 BAAI/bge-m3）" onChange={(event) => {
        const id = event.target.value;
        setModelInput({ ...modelInput, id, kind: modelInput.kind });
      }} />
      <input value={modelInput.name} disabled={working} maxLength={120} placeholder="显示名（可选）" onChange={(event) => setModelInput({ ...modelInput, name: event.target.value })} />
      <button
        className="model-kind-pill"
        type="button"
        data-kind={pendingKind}
        disabled={working}
        title="切换新增模型的类型"
        onClick={() => setModelInput({ ...modelInput, kind: nextModelKind(pendingKind) })}
      >
        {modelKindLabel(pendingKind)}
      </button>
      <button className="quiet-button" type="button" disabled={working || !modelInput.id.trim()} onClick={onAddModel}>添加</button>
    </div>
  </>;
}
