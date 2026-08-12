import { useEffect, useState } from "react";
import { Check, Cpu, Plus, RefreshCw, Trash2, X } from "lucide-react";

import { api } from "../lib/api";
import type { ProviderModel, ProviderPreset, ProviderSummary, SettingsSummary } from "../types";
import { IconButton } from "./common";

interface ProviderForm {
  name: string;
  base_url: string;
  api_key: string;
  model_default: string;
  models: ProviderModel[];
}

const emptyForm: ProviderForm = { name: "", base_url: "", api_key: "", model_default: "", models: [] };

/** P5G.4：模型供应商管理（列表 + 编辑表单 + 拉取模型 + 测试连接）。 */
export function ProviderManagerDialog({ settings, onClose, onChanged }: {
  settings: SettingsSummary;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [editing, setEditing] = useState<ProviderForm | null>(null);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [testMsg, setTestMsg] = useState<Record<string, string>>({});
  const [modelInput, setModelInput] = useState({ id: "", name: "" });

  useEffect(() => {
    void api.providerPresets().then((result) => setPresets(result.presets)).catch(() => setPresets([]));
  }, []);

  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  function startEdit(provider: ProviderSummary) {
    const form: ProviderForm = {
      name: provider.name,
      base_url: provider.base_url || "",
      api_key: "",
      model_default: provider.model || "",
      models: provider.models?.length ? provider.models : provider.model ? [{ id: provider.model, name: provider.model }] : [],
    };
    setEditing(form);
    setEditingName(provider.name);
    setError("");
    setNotice("");
  }

  function startAdd(preset?: ProviderPreset) {
    setEditing({
      ...emptyForm,
      name: preset?.name || "",
      base_url: preset?.base_url || "",
    });
    setEditingName(null);
    setError("");
    setNotice("");
  }

  async function testProvider(provider: ProviderSummary) {
    setTestMsg((current) => ({ ...current, [provider.name]: "正在测试…" }));
    try {
      const result = await api.providerTest(provider.name);
      setTestMsg((current) => ({ ...current, [provider.name]: `${result.latency_ms}ms · 连接正常` }));
    } catch (reason) {
      setTestMsg((current) => ({ ...current, [provider.name]: reason instanceof Error ? reason.message : "连接失败" }));
    }
  }

  async function fetchModels() {
    if (!editing) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const result = await api.fetchProviderModels(editing.base_url.trim(), editing.api_key.trim() || undefined);
      setEditing((current) => current && { ...current, models: result.models, model_default: current.model_default || result.models[0]?.id || "" });
      setNotice(`已获取 ${result.models.length} 个模型，可继续手输补充。`);
    } catch (reason) {
      setError(`${reason instanceof Error ? reason.message : "获取模型失败"}。可手动输入模型名。`);
    } finally {
      setWorking(false);
    }
  }

  function addModel() {
    const id = modelInput.id.trim();
    if (!editing || !id) return;
    if (editing.models.some((item) => item.id === id)) return;
    const next = [...editing.models, { id, name: modelInput.name.trim() || id }];
    setEditing({ ...editing, models: next, model_default: editing.model_default || id });
    setModelInput({ id: "", name: "" });
  }

  async function saveProvider() {
    if (!editing) return;
    const form = { ...editing };
    const name = form.name.trim();
    if (!name) { setError("请填写供应商名称。"); return; }
    if (!form.base_url.trim()) { setError("请填写 API 地址（base_url）。"); return; }
    if (!form.model_default && form.models.length) form.model_default = form.models[0].id;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      await api.saveProvider({
        name,
        base_url: form.base_url.trim(),
        type: "openai_compatible",
        provider_name: name,
        preset: editingName === name ? "" : (presets.find((item) => item.name === name)?.name || ""),
        api_key: form.api_key.trim() || null,
        model_default: form.model_default || null,
        models: form.models,
      });
      setNotice("已保存。");
      await onChanged();
      setEditing(null);
      setEditingName(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败。");
    } finally {
      setWorking(false);
    }
  }

  async function removeProvider(provider: ProviderSummary) {
    const suffix = provider.is_default
      ? "\n\n这是当前默认模型，删除后默认会失效，请先在「AI 与模型」里改选其它默认模型。"
      : "";
    if (!window.confirm(`删除供应商“${provider.name}”？其 API key 也会一并清除。${suffix}`)) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      await api.deleteProvider(provider.name);
      await onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败。");
    } finally {
      setWorking(false);
    }
  }

  return <section className="provider-manager" role="dialog" aria-modal="true" aria-label="管理模型供应商">
    <header className="provider-manager-header">
      <div><span>Providers</span><h2>模型供应商</h2><p>填写 API key 后即可使用。密钥明文保存在本地应用数据目录，不会写入资料库或日志。</p></div>
      <IconButton label="关闭供应商管理" onClick={onClose}><X /></IconButton>
    </header>
    {error && <div className="settings-error">{error}</div>}
    {notice && <div className="settings-notice"><Check size={14} />{notice}</div>}
    {!editing ? (
      <main className="provider-manager-main">
        <div className="provider-toolbar">
          <span>{settings.providers.length} 个供应商 · {settings.providers.filter((item) => item.configured).length} 个已配置</span>
          <button className="primary-button" disabled={working} onClick={() => startAdd()}><Plus size={15} />添加供应商</button>
        </div>
        {presets.length > 0 && <div className="provider-preset-row">
          <span>从模板添加：</span>
          {presets.map((preset) => <button key={preset.name} className="quiet-button" disabled={working} onClick={() => startAdd(preset)}>{preset.name}</button>)}
        </div>}
        <div className="provider-list">
          {settings.providers.map((provider) => (
            <article key={provider.name}>
              <span className={`provider-mark ${provider.configured ? "ready" : ""}`}><Cpu size={17} /></span>
              <div>
                <strong>{provider.name}{provider.is_default ? " · 默认" : ""}</strong>
                <small>{provider.model || "未设默认模型"}{provider.models?.length ? ` · ${provider.models.length} 个模型` : ""}{!provider.configured ? " · 未配置密钥" : ""}{testMsg[provider.name] ? ` · ${testMsg[provider.name]}` : ""}</small>
              </div>
              <div className="provider-actions">
                <button className="quiet-button" disabled={!provider.configured || working} onClick={() => void testProvider(provider)}>测试连接</button>
                <button className="quiet-button" disabled={working} onClick={() => startEdit(provider)}>编辑</button>
                <button className="quiet-button danger" disabled={working} onClick={() => void removeProvider(provider)}><Trash2 size={14} />删除</button>
              </div>
            </article>
          ))}
          {!settings.providers.length && <p className="settings-empty">还没有供应商。点击「添加供应商」或从模板添加。</p>}
        </div>
      </main>
    ) : (
      <main className="provider-manager-main">
        <div className="provider-editor">
          <label><span>名称</span><input value={editing.name} disabled={editingName !== null || working} maxLength={80} onChange={(event) => setEditing({ ...editing, name: event.target.value })} /></label>
          <label className="wide"><span>API 地址（base_url）</span><input value={editing.base_url} disabled={working} maxLength={300} placeholder="https://api.example.com/v1" onChange={(event) => setEditing({ ...editing, base_url: event.target.value })} /></label>
          <label className="wide"><span>API Key</span><input type="password" value={editing.api_key} disabled={working} autoComplete="off" placeholder={editingName !== null ? "留空 = 保持原密钥" : "sk-..."} onChange={(event) => setEditing({ ...editing, api_key: event.target.value })} /></label>
          <div className="provider-models-head">
            <span>模型列表</span>
            <button className="quiet-button" disabled={working || !editing.base_url.trim()} onClick={() => void fetchModels()}><RefreshCw size={13} />{working ? "获取中…" : "获取模型"}</button>
          </div>
          <p className="provider-models-hint">从「获取模型」拉取，或手动输入。默认模型用于该供应商的常规调用。</p>
          <label><span>默认模型</span><select className="settings-inline-select" value={editing.model_default} disabled={working} onChange={(event) => setEditing({ ...editing, model_default: event.target.value })}><option value="">跟随选择（未指定）</option>{editing.models.map((item) => <option key={item.id} value={item.id}>{item.name || item.id}</option>)}</select></label>
          <div className="provider-model-list">
            {editing.models.map((item) => <div key={item.id}><span>{item.name || item.id}<small>{item.id}</small></span><IconButton label={`删除模型 ${item.id}`} disabled={working} onClick={() => setEditing({ ...editing, models: editing.models.filter((m) => m.id !== item.id), model_default: editing.model_default === item.id ? "" : editing.model_default })}><Trash2 size={13} /></IconButton></div>)}
            {!editing.models.length && <p className="settings-empty">还没有模型。先「获取模型」或手动添加。</p>}
          </div>
          <div className="provider-model-add">
            <input value={modelInput.id} disabled={working} maxLength={120} placeholder="模型 ID（如 deepseek-chat）" onChange={(event) => setModelInput({ ...modelInput, id: event.target.value })} />
            <input value={modelInput.name} disabled={working} maxLength={120} placeholder="显示名（可选）" onChange={(event) => setModelInput({ ...modelInput, name: event.target.value })} />
            <button className="quiet-button" disabled={working || !modelInput.id.trim()} onClick={addModel}>添加</button>
          </div>
          <footer className="provider-editor-footer">
            <button className="quiet-button" disabled={working} onClick={() => { setEditing(null); setEditingName(null); setError(""); }}>取消</button>
            <button className="primary-button" disabled={working || !editing.name.trim() || !editing.base_url.trim()} onClick={() => void saveProvider()}><Check size={15} />保存供应商</button>
          </footer>
        </div>
      </main>
    )}
  </section>;
}
