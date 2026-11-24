import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Cpu, Plus, Trash2 } from "lucide-react";

import { api } from "../../../lib/api";
import { formatProviderCapability } from "../../../lib/retrievalStatus";
import type { ModelKind, ProviderPreset, ProviderSummary } from "../../../types";
import { ConfirmDialog } from "../../../ui/Modal";
import { ProviderFormFields } from "./ProviderFormFields";
import { classifyModelKind, resolveModelKind } from "./modelKind";
import { formFromPreset, formFromProvider, type ProviderForm } from "./providerForm";

function serializeProviderForm(form: ProviderForm | null): string {
  if (!form) return "";
  return JSON.stringify({
    name: form.name.trim(),
    base_url: form.base_url.trim().replace(/\/+$/, ""),
    api_key: form.api_key.trim(),
    model_default: form.model_default,
    models: form.models.map((m) => ({
      id: m.id,
      name: m.name || m.id,
      kind: resolveModelKind(m),
    })),
  });
}

/**
 * 供应商主从面板（2026-10-17 S3）。
 * 增强：未保存离开保护、编辑态 Escape 收回不误关外层设置弹窗、能力徽章一目了然、危险删除右对齐隔离。
 */
export function ProvidersPane({
  providers,
  onChanged,
  onDirtyChange,
}: {
  providers: ProviderSummary[];
  onChanged: () => Promise<void> | void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [selected, setSelected] = useState<string | null>(() => providers.find((item) => item.configured)?.name ?? providers[0]?.name ?? null);
  const [editing, setEditing] = useState<ProviderForm | null>(null);
  const [editingName, setEditingName] = useState<string | null>(null);
  const initialEditSnapRef = useRef<string>("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [testMsg, setTestMsg] = useState<Record<string, string>>({});
  const [modelInput, setModelInput] = useState<{ id: string; name: string; kind?: ModelKind }>({ id: "", name: "" });
  const [confirmDelete, setConfirmDelete] = useState<ProviderSummary | null>(null);
  const [pendingDiscard, setPendingDiscard] = useState<null | (() => void)>(null);

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

  const editingDirty = useMemo(() => {
    if (!editing) return false;
    return serializeProviderForm(editing) !== initialEditSnapRef.current;
  }, [editing]);

  useEffect(() => {
    onDirtyChange?.(editingDirty);
  }, [editingDirty, onDirtyChange]);

  useEffect(() => () => {
    onDirtyChange?.(false);
  }, [onDirtyChange]);

  function commitExitEdit() {
    setEditing(null);
    setEditingName(null);
    initialEditSnapRef.current = "";
  }

  function runGuarded(action: () => void) {
    if (editing && editingDirty) {
      setPendingDiscard(() => action);
      return;
    }
    action();
  }

  useEffect(() => {
    if (!editing || confirmDelete || pendingDiscard) return;
    const onEscapeCapture = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      if (editingDirty) {
        setPendingDiscard(() => () => {
          setEditing(null);
          setEditingName(null);
          initialEditSnapRef.current = "";
        });
      } else {
        setEditing(null);
        setEditingName(null);
        initialEditSnapRef.current = "";
      }
    };
    window.addEventListener("keydown", onEscapeCapture, true);
    return () => window.removeEventListener("keydown", onEscapeCapture, true);
  }, [confirmDelete, editing, editingDirty, pendingDiscard]);

  function startEdit(provider: ProviderSummary) {
    const form = formFromProvider(provider);
    initialEditSnapRef.current = serializeProviderForm(form);
    setEditing(form);
    setEditingName(provider.name);
    setError("");
    setNotice("");
  }

  function startAdd(preset?: ProviderPreset) {
    runGuarded(() => {
      const form = formFromPreset(preset);
      initialEditSnapRef.current = serializeProviderForm(form);
      setEditing(form);
      setEditingName(null);
      setError("");
      setNotice("");
    });
  }

  function cancelEdit() {
    runGuarded(commitExitEdit);
  }

  async function testProvider(provider: ProviderSummary) {
    setTestMsg((curr) => ({ ...curr, [provider.name]: "正在测试…" }));
    try {
      const result = await api.providerTest(provider.name);
      setTestMsg((curr) => ({ ...curr, [provider.name]: result.latency_ms + "ms · 连接正常" }));
    } catch (reason) {
      setTestMsg((curr) => ({ ...curr, [provider.name]: reason instanceof Error ? reason.message : "连接失败" }));
    }
  }

  async function fetchModels() {
    if (!editing) return;
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const result = await api.fetchProviderModels(
        editing.base_url.trim(),
        editing.api_key.trim() || undefined,
        editingName || editing.name.trim() || undefined,
      );
      const firstChat = result.models.find((item) => resolveModelKind(item) === "chat")?.id;
      setEditing((curr) => curr && {
        ...curr,
        models: result.models,
        model_default:
          curr.model_default && result.models.some((item) => item.id === curr.model_default && resolveModelKind(item) === "chat")
            ? curr.model_default
            : firstChat || curr.model_default || result.models[0]?.id || "",
      });
      if (result.models.length) setNotice("已获取 " + result.models.length + " 个模型，可继续手输或切换类型。");
      else setNotice("没有读取到模型，可手动添加。");
    } catch (reason) {
      const message = reason instanceof Error && reason.message ? reason.message.trim() : "获取模型失败";
      setError(message.includes("手动") ? message : `${message.replace(/[。.]$/, "")}。可手动输入模型 ID。`);
    } finally {
      setWorking(false);
    }
  }

  function addModel() {
    const id = modelInput.id.trim();
    if (!editing || !id) return;
    if (editing.models.some((item) => item.id === id)) return;
    const kind = modelInput.kind || classifyModelKind(id);
    const modelItem = kind === "chat"
      ? { id, name: modelInput.name.trim() || id }
      : { id, name: modelInput.name.trim() || id, kind };
    const next = [...editing.models, modelItem];
    setEditing({
      ...editing,
      models: next,
      model_default: editing.model_default || (kind === "chat" ? id : ""),
    });
    setModelInput({ id: "", name: "" });
  }

  async function saveProvider() {
    if (!editing) return;
    const form = { ...editing };
    const name = form.name.trim();
    if (!name) { setError("请填写供应商名称。"); return; }
    if (!form.base_url.trim()) { setError("请填写 API 地址（base_url）。"); return; }
    if (!form.model_default && form.models.length) {
      form.model_default = form.models.find((item) => resolveModelKind(item) === "chat")?.id || form.models[0].id;
    }
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
      commitExitEdit();
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
    return (
      <button
        key={provider.name}
        type="button"
        className={"providers-item" + (selected === provider.name ? " active" : "")}
        onClick={() => runGuarded(() => {
          setSelected(provider.name);
          commitExitEdit();
        })}
      >
        <span className="providers-dot" data-ready={provider.configured} />
        <Cpu size={15} />
        <span className="providers-name">{provider.name}</span>
        <small>{provider.models?.length || 0}</small>
      </button>
    );
  }

  const currentCapability = current ? formatProviderCapability(current) : null;

  return <div className="providers-pane">
    <div className="providers-list">
      <div className="providers-list-head">
        <span>{providers.length} 个供应商 · {configured.length} 已配置</span>
        <button className="quiet-button" type="button" disabled={working} onClick={() => startAdd()}><Plus size={13} />新增</button>
      </div>
      {configured.length > 0 && <div className="providers-group"><span className="providers-group-label">已配置</span>{configured.map(renderItem)}</div>}
      {unconfigured.length > 0 && <div className="providers-group"><span className="providers-group-label">未配置</span>{unconfigured.map(renderItem)}</div>}
      {custom.length > 0 && <div className="providers-group"><span className="providers-group-label">自定义</span>{custom.map(renderItem)}</div>}
      {presets.some((preset) => !providers.some((item) => item.name === preset.name)) && <div className="providers-group">
        <span className="providers-group-label">从模板添加</span>
        {presets.filter((preset) => !providers.some((item) => item.name === preset.name)).map((preset) => (
          <button key={preset.name} type="button" className="providers-item dim" disabled={working} title={(preset.note || preset.name) + " · " + preset.base_url} onClick={() => startAdd(preset)}>
            <span className="providers-dot" />
            <Plus size={14} />
            <span className="providers-name">{preset.name}</span>
            <small>{preset.auth_type === "none" ? "本地" : ""}</small>
          </button>
        ))}
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
        <div className="providers-detail-head">
          <strong>{current.name}</strong>
          {current.is_default && <i>默认</i>}
          {currentCapability && (
            <span className="providers-cap-badge" data-tone={currentCapability.tone}>
              {currentCapability.badge}
            </span>
          )}
        </div>
        <p className="settings-model-hint">{current.base_url || "未填写 API 地址"}</p>
        <div className="providers-detail-meta">
          <span>默认对话模型：{current.model || "未设置"}</span>
          <span>模型：{current.models?.length || 0} 个{(() => {
            const embCount = (current.models || []).filter((item) => resolveModelKind(item) === "embedding").length;
            return embCount > 0 ? `（含 ${embCount} 个向量）` : "";
          })()}</span>
          <span>{current.configured ? "已配置" : "未配置密钥"}</span>
        </div>
        {currentCapability && (
          <p className="settings-model-hint">{currentCapability.note}</p>
        )}
        <div className="providers-detail-actions">
          <button className="quiet-button" type="button" disabled={!current.configured || working} onClick={() => void testProvider(current)}>测试连接</button>
          <button className="quiet-button" type="button" disabled={working} onClick={() => startEdit(current)}>编辑</button>
          <button className="quiet-button danger providers-delete-btn" type="button" disabled={working} onClick={() => setConfirmDelete(current)}><Trash2 size={13} />删除</button>
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
    {pendingDiscard && <ConfirmDialog
      danger
      title="放弃未保存的供应商修改？"
      detail="离开当前表单后，尚未保存的地址、密钥或模型改动将会丢失。"
      confirmLabel="放弃修改"
      cancelLabel="继续编辑"
      onCancel={() => setPendingDiscard(null)}
      onConfirm={() => {
        const fn = pendingDiscard;
        setPendingDiscard(null);
        fn();
      }}
    />}
  </div>;
}
