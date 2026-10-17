import { useEffect, useState } from "react";
import { Check, Cpu, Plus, Trash2 } from "lucide-react";

import { api } from "../../../lib/api";
import type { ProviderPreset, ProviderSummary } from "../../../types";
import { ConfirmDialog } from "../../../ui/Modal";
import { ProviderFormFields } from "./ProviderFormFields";
import { formFromPreset, formFromProvider, type ProviderForm } from "./providerForm";

/**
 * 供应商主从面板（2026-10-17 S3：取代 ProviderManagerDialog 嵌套弹窗）。
 * 左列：已配置 / 未配置 / 自定义 + 模板入口；右列：详情或编辑表单。逻辑与原弹窗一致。
 */
export function ProvidersPane({ providers, onChanged }: {
  providers: ProviderSummary[];
  onChanged: () => Promise<void> | void;
}) {
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [selected, setSelected] = useState<string | null>(() => providers.find((item) => item.configured)?.name ?? providers[0]?.name ?? null);
  const [editing, setEditing] = useState<ProviderForm | null>(null);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [testMsg, setTestMsg] = useState<Record<string, string>>({});
  const [modelInput, setModelInput] = useState({ id: "", name: "" });
  const [confirmDelete, setConfirmDelete] = useState<ProviderSummary | null>(null);

  useEffect(() => {
    void api.providerPresets().then((result) => setPresets(result.presets)).catch(() => setPresets([]));
  }, []);

  useEffect(() => {
    if (selected && providers.some((item) => item.name === selected)) return;
    const fallback = providers.find((item) => item.configured)?.name ?? providers[0]?.name ?? null;
    if (fallback) setSelected(fallback);
  }, [providers, selected]);

  const configured = providers.filter((item) => item.configured);
  const unconfigured = providers.filter((item) => !item.configured);
  const presetNames = new Set(presets.map((item) => item.name));
  const custom = providers.filter((item) => !presetNames.has(item.name));
  const current = selected ? providers.find((item) => item.name === selected) || null : null;
  const editingPreset = presets.find((item) => item.name === editing?.name);
  const editingKeyless = Boolean(editingPreset?.keyless || editingPreset?.auth_type === "none" || editingPreset?.auth_type === "optional");

  function startEdit(provider: ProviderSummary) {
    setEditing(formFromProvider(provider));
    setEditingName(provider.name);
    setError("");
    setNotice("");
  }

  function startAdd(preset?: ProviderPreset) {
    setEditing(formFromPreset(preset));
    setEditingName(null);
    setError("");
    setNotice("");
  }

  function cancelEdit() {
    setEditing(null);
    setEditingName(null);
  }

  async function testProvider(provider: ProviderSummary) {
    setTestMsg((current) => ({ ...current, [provider.name]: "正在测试…" }));
    try {
      const result = await api.providerTest(provider.name);
      setTestMsg((current) => ({ ...current, [provider.name]: result.latency_ms + "ms · 连接正常" }));
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
      if (result.models.length) setNotice("已获取 " + result.models.length + " 个模型，可继续手输补充。");
      else setNotice("没有读取到模型，可手动添加。");
    } catch (reason) {
      setError((reason instanceof Error ? reason.message : "获取模型失败") + "。可手动输入模型名。");
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
        type: presets.find((item) => item.name === name)?.type || "openai_compatible",
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
      setSelected(name);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败。");
    } finally {
      setWorking(false);
    }
  }

  async function removeProvider(provider: ProviderSummary) {
    setWorking(true);
    setError("");
    setNotice("");
    try {
      await api.deleteProvider(provider.name);
      await onChanged();
      setNotice("已删除 " + provider.name + "。");
      setSelected(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败。");
    } finally {
      setWorking(false);
      setConfirmDelete(null);
    }
  }

  function renderItem(provider: ProviderSummary) {
    return <button key={provider.name} type="button" className={"providers-item" + (selected === provider.name ? " active" : "")} onClick={() => { setSelected(provider.name); setEditing(null); setEditingName(null); }}>
      <span className="providers-dot" data-ready={provider.configured} />
      <Cpu size={15} />
      <span className="providers-name">{provider.name}</span>
      <small>{provider.models?.length || 0}</small>
    </button>;
  }

  return <div className="providers-pane">
    <div className="providers-list">
      <div className="providers-list-head">
        <span>{providers.length} 个供应商 · {configured.length} 已配置</span>
        <button className="quiet-button" type="button" disabled={working} onClick={() => startAdd()}><Plus size={13} />新增</button>
      </div>
      {configured.length > 0 && <div className="providers-group"><span className="providers-group-label">已配置</span>{configured.map(renderItem)}</div>}
      {unconfigured.length > 0 && <div className="providers-group"><span className="providers-group-label">未配置</span>{unconfigured.map(renderItem)}</div>}
      {custom.length > 0 && <div className="providers-group"><span className="providers-group-label">自定义</span>{custom.map(renderItem)}</div>}
      {presets.length > 0 && <div className="providers-group">
        <span className="providers-group-label">从模板添加</span>
        <div className="providers-presets">
          {presets.map((preset) => <button key={preset.name} type="button" className="quiet-button" disabled={working} title={preset.note || preset.base_url} onClick={() => startAdd(preset)}>{preset.note || preset.name}</button>)}
        </div>
      </div>}
    </div>
    <div className="providers-detail">
      {error && <div className="settings-error">{error}</div>}
      {notice && <div className="settings-notice"><Check size={14} />{notice}</div>}
      {editing ? <>
        <div className="providers-detail-head"><strong>{editingName ? "编辑 " + editingName : "添加供应商"}</strong></div>
        <ProviderFormFields form={editing} setForm={setEditing} working={working} keyless={editingKeyless} onFetchModels={() => void fetchModels()} modelInput={modelInput} setModelInput={setModelInput} onAddModel={addModel} onRemoveModel={(id) => setEditing({ ...editing, models: editing.models.filter((item) => item.id !== id), model_default: editing.model_default === id ? "" : editing.model_default })} />
        <div className="providers-detail-actions">
          <button className="quiet-button" type="button" disabled={working} onClick={cancelEdit}>取消</button>
          <button className="primary-button" type="button" disabled={working || !editing.name.trim() || !editing.base_url.trim()} onClick={() => void saveProvider()}>保存</button>
        </div>
      </> : current ? <>
        <div className="providers-detail-head"><strong>{current.name}</strong>{current.is_default && <i>默认</i>}</div>
        <p className="settings-model-hint">{current.base_url || "未填写 API 地址"}</p>
        <div className="providers-detail-meta">
          <span>默认模型：{current.model || "未设置"}</span>
          <span>模型：{current.models?.length || 0} 个</span>
          <span>{current.configured ? "已配置" : "未配置密钥"}</span>
        </div>
        <div className="providers-detail-actions">
          <button className="quiet-button" type="button" disabled={!current.configured || working} onClick={() => void testProvider(current)}>测试连接</button>
          <button className="quiet-button" type="button" disabled={working} onClick={() => startEdit(current)}>编辑</button>
          <button className="quiet-button danger" type="button" disabled={working} onClick={() => setConfirmDelete(current)}><Trash2 size={13} />删除</button>
        </div>
        {testMsg[current.name] && <p className="settings-model-hint">{testMsg[current.name]}</p>}
      </> : <p className="settings-empty">从左侧选择一个供应商，或从模板添加。</p>}
    </div>
    {confirmDelete && <ConfirmDialog
      busy={working}
      danger
      title={"删除供应商「" + confirmDelete.name + "」？"}
      detail={<>其 API key 也会一并清除。{confirmDelete.is_default && <strong>这是当前默认模型，删除后默认会失效，请先在「AI 与模型」里改选其它默认模型。</strong>}</>}
      confirmLabel="删除供应商"
      onCancel={() => setConfirmDelete(null)}
      onConfirm={() => void removeProvider(confirmDelete)}
    />}
  </div>;
}
