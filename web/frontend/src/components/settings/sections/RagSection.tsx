import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, RefreshCw, Sparkles } from "lucide-react";

import { api } from "../../../lib/api";
import type {
  RagEmbeddingMode,
  RagSettingsResponse,
} from "../../../types";
import { ConfirmDialog } from "../../../ui/Modal";
import { SettingsRow, SettingsSection, SettingsSegmented } from "../SettingsPrimitives";
import { RagSearchTestCard } from "./RagSearchTestCard";

interface FormState {
  mode: "disabled" | "provider" | "custom" | "ollama";
  provider_name: string;
  preset: string;
  base_url: string;
  model: string;
  api_key: string;
  clear_api_key: boolean;
  dim: string;
  ollama_url: string;
  ollama_model: string;
}

function initialFormFromRag(rag: RagSettingsResponse): FormState {
  const { config, status, presets, reusable_providers } = rag;
  const supportedConfigured = reusable_providers.filter(
    (item) => item.configured && item.supports_embedding !== false,
  );
  let formMode: FormState["mode"];
  if (config.mode === "disabled") {
    formMode = "disabled";
  } else if (config.mode === "ollama") {
    formMode = "ollama";
  } else if (config.mode === "provider") {
    formMode = "provider";
  } else if (config.mode === "custom") {
    formMode = "custom";
  } else {
    // mode === "auto"
    if (status.active_provider === "ollama" && status.provider_ready) {
      formMode = "ollama";
    } else if (config.has_api_key && supportedConfigured.some((item) => item.name === config.preset)) {
      formMode = "provider";
    } else {
      formMode = "custom";
    }
  }
  const activePreset = presets.find((item) => item.id === (config.preset || "siliconflow")) || presets[0];
  const defaultProvider = config.provider_name
    || supportedConfigured.find((item) => item.name !== "ollama")?.name
    || supportedConfigured[0]?.name
    || "";

  return {
    mode: formMode,
    provider_name: defaultProvider,
    preset: config.preset || activePreset?.id || "siliconflow",
    base_url: config.base_url || activePreset?.base_url || "",
    model: config.model || activePreset?.default_model || "",
    api_key: "",
    clear_api_key: false,
    dim: config.dim ? String(config.dim) : (activePreset?.dim ? String(activePreset.dim) : ""),
    ollama_url: config.ollama_url || "http://localhost:11434",
    ollama_model: config.ollama_model || "qwen3-embedding:0.6b",
  };
}

function formToPayload(form: FormState): Record<string, unknown> {
  const dimNumber = Number(form.dim);
  return {
    mode: form.mode as RagEmbeddingMode,
    provider_name: form.mode === "provider" ? form.provider_name : "",
    preset: form.mode === "custom" ? form.preset : "",
    base_url: form.mode === "custom" ? form.base_url.trim() : "",
    model: form.mode === "provider" || form.mode === "custom" ? form.model.trim() : "",
    api_key: form.mode === "custom" ? form.api_key.trim() : "",
    clear_api_key: form.mode === "custom" ? form.clear_api_key : false,
    dim: form.mode === "custom" && Number.isInteger(dimNumber) && dimNumber > 0 ? dimNumber : null,
    ollama_url: form.ollama_url.trim() || "http://localhost:11434",
    ollama_model: form.ollama_model.trim() || "qwen3-embedding:0.6b",
  };
}

function retrievalModeLabel(mode: RagSettingsResponse["status"]["effective_mode"]): string {
  if (mode === "hybrid") return "hybrid · 向量 + 全文融合";
  if (mode === "fts_only") return "fts_only · 仅纯文本关键词";
  return "waiting · 等待导入资料";
}

function statusTone(status: RagSettingsResponse["status"]): "ready" | "warn" | "muted" {
  if (!status.knowledge_ready) return "muted";
  if (status.needs_rebuild || status.signature_mismatch) return "warn";
  if (status.embedding_available && status.needs_backfill) return "warn";
  if (status.effective_mode === "hybrid") return "ready";
  return "muted";
}

/** 设置 · 检索与 RAG：人话分工解释 + 实时能力诊断 + 向导式向量配置 + 召回测试。 */
export function RagSection({
  onOpenModels,
  onStatusInvalidated,
}: {
  onOpenModels?: () => void;
  onStatusInvalidated?: () => void;
}) {
  const [rag, setRag] = useState<RagSettingsResponse | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [testFeedback, setTestFeedback] = useState<{ tone: "ready" | "warn"; text: string } | null>(null);
  const [confirmSaveRebuild, setConfirmSaveRebuild] = useState(false);

  const loadRag = useCallback(async (resetForm = true) => {
    setLoading(true);
    setError("");
    try {
      const next = await api.ragSettings();
      setRag(next);
      if (resetForm) setForm(initialFormFromRag(next));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取检索配置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRag(true);
  }, [loadRag]);

  const activePreset = useMemo(
    () => rag?.presets.find((item) => item.id === form?.preset) || null,
    [rag, form?.preset],
  );

  const supportedReusable = useMemo(
    () => (rag?.reusable_providers || []).filter((item) => item.configured && item.supports_embedding !== false),
    [rag],
  );

  const chatOnlyConfigured = useMemo(
    () => (rag?.reusable_providers || []).filter((item) => item.configured && item.supports_embedding === false),
    [rag],
  );

  const selectedReusable = useMemo(
    () => supportedReusable.find((item) => item.name === form?.provider_name) || supportedReusable[0] || null,
    [supportedReusable, form?.provider_name],
  );

  const matchingProviderForPreset = useMemo(() => {
    if (!rag || !form || form.mode !== "custom") return null;
    return rag.reusable_providers.find(
      (item) => item.configured && item.preset && item.preset === form.preset,
    ) || null;
  }, [rag, form]);

  function selectPreset(presetId: string) {
    if (!rag || !form) return;
    const preset = rag.presets.find((item) => item.id === presetId);
    if (!preset) return;
    setTestFeedback(null);
    setForm({
      ...form,
      preset: preset.id,
      base_url: preset.base_url,
      model: preset.default_model,
      dim: preset.dim ? String(preset.dim) : "",
      clear_api_key: false,
    });
  }

  function switchMode(nextMode: FormState["mode"]) {
    if (!rag || !form) return;
    setTestFeedback(null);
    setError("");
    setNotice("");
    if (nextMode === "provider" && selectedReusable) {
      const defaultEmbModel = selectedReusable.embedding_models[0]?.id || (selectedReusable.preset === "ollama" ? "qwen3-embedding:0.6b" : "");
      setForm({
        ...form,
        mode: nextMode,
        provider_name: selectedReusable.name,
        model: form.mode === "provider" && form.model ? form.model : defaultEmbModel,
      });
      return;
    }
    setForm({ ...form, mode: nextMode });
  }

  async function runEmbeddingTest() {
    if (!form) return;
    setTesting(true);
    setError("");
    setTestFeedback(null);
    try {
      const result = await api.testRagEmbedding(formToPayload(form));
      setTestFeedback({
        tone: "ready",
        text: `连接成功 · ${result.model || result.provider} · ${result.dim} 维 · ${result.latency_ms}ms`,
      });
    } catch (reason) {
      setTestFeedback({
        tone: "warn",
        text: reason instanceof Error ? reason.message : "向量模型测试失败",
      });
    } finally {
      setTesting(false);
    }
  }

  function willInvalidateExistingVectors(): boolean {
    if (!rag || !form) return false;
    const indexed = rag.status.vector_stats.vector_indexed || 0;
    if (indexed <= 0) return false;
    const storedModel = rag.status.stored_signature?.model || "";
    if (!storedModel) return false;
    if (form.mode === "disabled") return true;
    const targetModel = form.mode === "ollama" ? form.ollama_model.trim() : form.model.trim();
    return Boolean(targetModel && targetModel !== storedModel);
  }

  async function commitSave() {
    if (!form) return;
    setSaving(true);
    setError("");
    setNotice("");
    setConfirmSaveRebuild(false);
    try {
      const updated = await api.saveRagSettings(formToPayload(form));
      setRag(updated);
      setForm(initialFormFromRag(updated));
      onStatusInvalidated?.();
      if (updated.status.needs_rebuild) {
        setNotice("配置已保存。当前切换了向量模型，请点击上方「重建全部向量索引」后启用新模型语义检索。");
      } else if (updated.status.needs_backfill) {
        setNotice("配置已保存。向量模型已就绪，点击上方即可为现有资料补建向量。");
      } else {
        setNotice("检索与向量配置已保存并生效。");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存检索配置失败");
    } finally {
      setSaving(false);
    }
  }

  function handleSaveClick() {
    if (willInvalidateExistingVectors()) {
      setConfirmSaveRebuild(true);
      return;
    }
    void commitSave();
  }

  async function runBackfill(rebuild: boolean) {
    setBackfilling(true);
    setError("");
    setNotice("");
    try {
      const response = await api.backfillRagVectors(rebuild);
      setRag(response.rag);
      setForm(initialFormFromRag(response.rag));
      onStatusInvalidated?.();
      const { result } = response;
      const errCount = result.vector_stats.vector_error || 0;
      const actionLabel = result.rebuilt ? "重建" : "补建";
      setNotice(
        `已完成向量${actionLabel}：新增/更新 ${result.backfilled} 份（已索引 ${result.vector_stats.vector_indexed}/${result.vector_stats.documents} 份，${result.dim} 维）${errCount > 0 ? `，另有 ${errCount} 份失败` : ""}。`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "向量索引建立失败");
    } finally {
      setBackfilling(false);
    }
  }

  const status = rag?.status;
  const tone = status ? statusTone(status) : "muted";
  const pendingTotal = status ? (status.vector_stats.vector_pending + status.vector_stats.vector_error) : 0;

  return <>
    <SettingsSection
      title="当前检索能力"
      description="先看一眼「对话模型」和「向量模型」各管什么，再看当前资料库能不能做语义检索。"
    >
      <div className="rag-role-primer">
        <div>
          <strong>对话模型（在「AI 与模型」配）</strong>
          <p>负责聊天回答、讲题出题、整理笔记，如 DeepSeek、MiniMax。DeepSeek 官方目前不提供向量接口。</p>
        </div>
        <div>
          <strong>向量模型（就在本页配 · 可选）</strong>
          <p>把资料切成语义向量，搜“防过拟合”也能召回只写着“Dropout / 正则化”的段落；不配时自动走纯文本关键词检索。</p>
        </div>
      </div>

      {loading && !rag ? (
        <p className="settings-empty">正在检测检索与向量状态…</p>
      ) : status ? <>
        <div className="rag-status-banner" data-tone={tone}>
          <span className="rag-status-icon">
            {tone === "ready" ? <CheckCircle2 size={16} /> : tone === "warn" ? <AlertTriangle size={16} /> : <Database size={16} />}
          </span>
          <div className="rag-status-copy">
            <strong>{status.semantic_status.title}</strong>
            <p>{status.semantic_status.detail}</p>
            {status.semantic_status.action && <small>{status.semantic_status.action}</small>}
          </div>
          {(status.needs_rebuild || status.needs_backfill) && (
            <button
              className="primary-button"
              type="button"
              disabled={backfilling || saving}
              onClick={() => void runBackfill(status.needs_rebuild)}
            >
              <RefreshCw size={13} />
              {backfilling
                ? "正在建向量…"
                : status.needs_rebuild
                  ? `重建向量索引（${status.vector_stats.documents} 份）`
                  : `为 ${pendingTotal} 份资料补建向量`}
            </button>
          )}
        </div>

        <div className="rag-metrics">
          <div>
            <span>当前检索模式</span>
            <strong>{retrievalModeLabel(status.effective_mode)}</strong>
          </div>
          <div>
            <span>向量模型</span>
            <strong>
              {status.display_provider === "disabled"
                ? "已关闭（仅纯文本）"
                : status.active_model
                  ? `${status.display_provider || status.active_provider} · ${status.active_model}${status.active_dim ? ` · ${status.active_dim}\u00A0维` : ""}`
                  : "未配置"}
            </strong>
          </div>
          <div>
            <span>资料向量覆盖率</span>
            <strong>
              {status.knowledge_ready
                ? `${status.vector_stats.vector_indexed} / ${status.vector_stats.documents} 份已建向量`
                : "等待导入资料"}
            </strong>
          </div>
        </div>

        {status.error_samples.length > 0 && (
          <div className="rag-error-list">
            <strong>最近向量化失败示例（仅展示前 {status.error_samples.length} 条）</strong>
            {status.error_samples.map((sample) => (
              <div key={sample.source}>
                <span>{sample.title || sample.source}</span>
                <small>{sample.error}</small>
              </div>
            ))}
          </div>
        )}
      </> : null}
    </SettingsSection>

    <SettingsSection
      title="向量模型配置"
      description="配置只保存在本机 ~/.bobodan/provider.json，绝不写入 config.yaml 或导出备份；不懂怎么选可直接用「硅基流动 · BAAI/bge-m3」。"
      footer={form ? (
        <>
          <button
            className="quiet-button"
            type="button"
            disabled={testing || saving || form.mode === "disabled"}
            onClick={() => void runEmbeddingTest()}
          >
            {testing ? "正在测试…" : "测试向量模型"}
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={saving || testing}
            onClick={handleSaveClick}
          >
            {saving ? "保存中…" : "保存配置"}
          </button>
        </>
      ) : undefined}
    >
      {error && <div className="settings-error">{error}</div>}
      {notice && <div className="settings-notice">{notice}</div>}
      {testFeedback && (
        <div className="rag-feedback" data-tone={testFeedback.tone}>
          {testFeedback.text}
        </div>
      )}

      {form && <>
        <SettingsRow label="配置方式" hint="如果「AI 与模型」里已经配过硅基流动/百炼/智谱/OpenAI，可直接复用密钥。">
          <SettingsSegmented
            label="向量配置方式"
            value={form.mode}
            onChange={switchMode}
            options={[
              { value: "disabled", label: "仅纯文本" },
              { value: "provider", label: "复用已有供应商" },
              { value: "custom", label: "云端向量 API" },
              { value: "ollama", label: "本地 Ollama" },
            ]}
          />
        </SettingsRow>

        {form.mode === "disabled" && (
          <div className="rag-mode-note">
            <p>仅走本地 SQLite FTS5 全文 + 中文 2-gram 匹配：零 API 费用、资料片段绝不发往外部向量服务，专有名词和精确表达可直接命中。</p>
          </div>
        )}

        {form.mode === "provider" && (
          <div className="rag-provider-box">
            {supportedReusable.length > 0 ? (
              <div className="rag-provider-list">
                {supportedReusable.map((provider) => {
                  const selected = selectedReusable?.name === provider.name;
                  return (
                    <label className="rag-provider-card" key={provider.name} data-selected={selected ? "true" : "false"}>
                      <input
                        type="radio"
                        name="rag-reusable-provider"
                        checked={selected}
                        onChange={() => {
                          setTestFeedback(null);
                          const defaultModel = provider.embedding_models[0]?.id
                            || (provider.preset === "ollama" ? "qwen3-embedding:0.6b" : "");
                          setForm({ ...form, provider_name: provider.name, model: defaultModel });
                        }}
                      />
                      <div>
                        <strong>{provider.name}</strong>
                        <small>{provider.keyless ? "免密钥本地服务" : "复用已保存 API Key"} · {provider.base_url}</small>
                      </div>
                    </label>
                  );
                })}
              </div>
            ) : (
              <div className="rag-mode-note">
                <p>
                  目前「AI 与模型」里还没有可直接用于向量的已配置供应商。
                  {chatOnlyConfigured.length > 0
                    ? `（已配置的 ${chatOnlyConfigured.map((item) => item.name).join("、")} 仅支持对话生成，不提供向量 API。）`
                    : ""}
                </p>
                <div className="rag-inline-actions">
                  <button className="quiet-button" type="button" onClick={() => switchMode("custom")}>
                    <Sparkles size={13} />去「云端向量 API」填硅基流动 Key
                  </button>
                  {onOpenModels && (
                    <button className="quiet-button" type="button" onClick={onOpenModels}>
                      去「AI 与模型」添加供应商
                    </button>
                  )}
                </div>
              </div>
            )}

            {selectedReusable && (
              <>
                {selectedReusable.embedding_models.length > 0 && (
                  <div className="rag-chip-row">
                    <span>推荐模型：</span>
                    {selectedReusable.embedding_models.map((item) => (
                      <button
                        type="button"
                        key={item.id}
                        className="rag-chip"
                        data-active={form.model === item.id ? "true" : "false"}
                        onClick={() => setForm({ ...form, model: item.id })}
                      >
                        {item.id}
                      </button>
                    ))}
                  </div>
                )}
                <label className="settings-field">
                  <span>向量模型 ID</span>
                  <input
                    value={form.model}
                    maxLength={120}
                    placeholder={selectedReusable.preset === "ollama" ? "qwen3-embedding:0.6b" : "例如 BAAI/bge-m3"}
                    onChange={(event) => setForm({ ...form, model: event.target.value })}
                  />
                  <small>注意不要选对话模型（例如 deepseek-chat）。</small>
                </label>
              </>
            )}

            {chatOnlyConfigured.length > 0 && supportedReusable.length > 0 && (
              <p className="settings-model-hint">
                说明：{chatOnlyConfigured.map((item) => item.name).join("、")} 仅用于聊天问答，不能用来建资料向量。
              </p>
            )}
          </div>
        )}

        {form.mode === "custom" && (
          <div className="rag-custom-box">
            <div className="rag-preset-grid">
              {(rag?.presets || []).map((preset) => (
                <button
                  type="button"
                  key={preset.id}
                  className="rag-preset-card"
                  data-selected={form.preset === preset.id ? "true" : "false"}
                  onClick={() => selectPreset(preset.id)}
                >
                  <strong>{preset.label}</strong>
                  <small>{preset.badge}</small>
                </button>
              ))}
            </div>

            {activePreset && <p className="settings-model-hint">{activePreset.description}</p>}

            {activePreset && activePreset.suggested_models.length > 0 && (
              <div className="rag-chip-row">
                <span>模型快捷选择：</span>
                {activePreset.suggested_models.map((modelId) => (
                  <button
                    type="button"
                    key={modelId}
                    className="rag-chip"
                    data-active={form.model === modelId ? "true" : "false"}
                    onClick={() => setForm({
                      ...form,
                      model: modelId,
                      dim: modelId === activePreset.default_model && activePreset.dim ? String(activePreset.dim) : "",
                    })}
                  >
                    {modelId}
                  </button>
                ))}
              </div>
            )}

            <label className="settings-field">
              <span>API Key</span>
              <input
                type="password"
                value={form.api_key}
                autoComplete="off"
                placeholder={
                  matchingProviderForPreset
                    ? `留空可自动复用「AI 与模型 → ${matchingProviderForPreset.name}」的密钥`
                    : rag?.config.has_api_key && rag.config.api_key_source === "saved" && form.preset === rag.config.preset
                      ? "已保存密钥（留空 = 保持不变）"
                      : "粘贴该平台的 API Key（sk-...）"
                }
                onChange={(event) => setForm({ ...form, api_key: event.target.value, clear_api_key: false })}
              />
              {rag?.config.api_key_source === "saved" && !form.api_key && (
                <small>
                  本机已保存向量密钥；
                  <button
                    type="button"
                    className="text-link"
                    onClick={() => setForm({ ...form, clear_api_key: true })}
                  >
                    {form.clear_api_key ? "将在保存时清除密钥" : "清除已保存密钥"}
                  </button>
                </small>
              )}
            </label>

            <details className="rag-advanced" open={form.preset === "custom"}>
              <summary>高级参数：接口地址、模型名与维度（常规用户保持默认即可）</summary>
              <label className="settings-field">
                <span>API 地址（base_url）</span>
                <input
                  value={form.base_url}
                  maxLength={300}
                  placeholder="https://api.siliconflow.cn/v1"
                  onChange={(event) => setForm({ ...form, base_url: event.target.value })}
                />
                <small>填写服务根路径即可，系统会自动请求 /embeddings，请勿手动加后缀。</small>
              </label>
              <label className="settings-field">
                <span>向量模型 ID</span>
                <input
                  value={form.model}
                  maxLength={120}
                  placeholder="BAAI/bge-m3"
                  onChange={(event) => setForm({ ...form, model: event.target.value })}
                />
              </label>
              <label className="settings-field">
                <span>向量维度（可选，留空首次测试/建库自动探测）</span>
                <input
                  type="number"
                  min={1}
                  max={16384}
                  value={form.dim}
                  placeholder="自动探测"
                  onChange={(event) => setForm({ ...form, dim: event.target.value })}
                />
              </label>
            </details>

            <p className="settings-model-hint">
              数据边界：启用云端向量后，资料切片正文会按需发往所选服务商计算向量；聊天时不经过该接口。
            </p>
          </div>
        )}

        {form.mode === "ollama" && (
          <div className="rag-custom-box">
            <label className="settings-field">
              <span>Ollama 服务地址</span>
              <input
                value={form.ollama_url}
                maxLength={300}
                placeholder="http://localhost:11434"
                onChange={(event) => setForm({ ...form, ollama_url: event.target.value })}
              />
            </label>
            <label className="settings-field">
              <span>本地向量模型名称</span>
              <input
                value={form.ollama_model}
                maxLength={120}
                placeholder="qwen3-embedding:0.6b"
                onChange={(event) => setForm({ ...form, ollama_model: event.target.value })}
              />
              <small>离线免费运行：确保本机 Ollama 已启动并拉取模型，例如 `ollama pull {form.ollama_model || "qwen3-embedding:0.6b"}`。</small>
            </label>
          </div>
        )}
      </>}
    </SettingsSection>

    <RagSearchTestCard knowledgeReady={Boolean(status?.knowledge_ready)} />

    <SettingsSection
      title="术语与检索机制（高级）"
      description="折叠供进阶排查：请求模式（auto / hybrid / directory）与实际汇报模式不是同一套词。"
    >
      <details className="rag-glossary-details">
        <summary>展开检索术语词汇表</summary>
        <dl className="rag-glossary">
          <div><dt>hybrid</dt><dd>向量召回 + 全文检索 → RRF 融合；语义和关键词同时生效。</dd></div>
          <div><dt>fts_only</dt><dd>向量不可用时的安全降级：只走 SQLite FTS5（中文 2-gram）。</dd></div>
          <div><dt>unavailable</dt><dd>索引不存在或未同步，检索不可用。</dd></div>
          <div><dt>directory / directory_grep</dt><dd>按资料目录路由到具体文档，再在原文里定位段落。</dd></div>
        </dl>
      </details>
    </SettingsSection>

    {confirmSaveRebuild && (
      <ConfirmDialog
        busy={saving}
        title="切换向量模型将使旧向量暂停生效"
        detail={
          <>
            当前资料库已有 {status?.vector_stats.vector_indexed || 0} 份资料使用「{status?.stored_signature?.model}」建过向量。不同向量模型的空间不兼容，保存新配置后会先安全回退到纯文本检索，你可在页面顶部点击一次「重建向量索引」。
          </>
        }
        confirmLabel="保存并继续"
        onCancel={() => setConfirmSaveRebuild(false)}
        onConfirm={() => void commitSave()}
      />
    )}
  </>;
}
