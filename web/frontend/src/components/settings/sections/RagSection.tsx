import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, CheckCircle2, Copy, Database, KeyRound, RefreshCw, Sparkles, Square } from "lucide-react";

import { api } from "../../../lib/api";
import {
  formatEffectiveModeLabel,
  formatRetrievalBadge,
  originOfUrl,
} from "../../../lib/retrievalStatus";
import { useRagBackfillStore } from "../../../stores/ragBackfillStore";
import type {
  RagOllamaDiscoveryResponse,
  RagSettingsResponse,
} from "../../../types";
import { ConfirmDialog } from "../../../ui/Modal";
import { SettingsSection } from "../SettingsPrimitives";
import { RagSearchTestCard } from "./RagSearchTestCard";

type UiRagMode = "disabled" | "cloud" | "ollama";

interface CloudDraft {
  preset: string;
  base_url: string;
  model: string;
  api_key: string;
  clear_api_key: boolean;
  dim: string;
}

interface OllamaDraft {
  url: string;
  model: string;
}

interface RagDrafts {
  uiMode: UiRagMode;
  cloud: CloudDraft;
  ollama: OllamaDraft;
}

const DEFAULT_OLLAMA_URL = "http://localhost:11434";
const DEFAULT_OLLAMA_MODEL = "qwen3-embedding:0.6b";
const RECOMMENDED_OLLAMA_MODELS = ["qwen3-embedding:0.6b", "bge-m3", "nomic-embed-text"];

function deriveSavedUiMode(rag: RagSettingsResponse): UiRagMode {
  const { config, status } = rag;
  if (config.mode === "disabled") return "disabled";
  if (
    config.mode === "ollama"
    || (config.mode === "provider" && config.provider_name === "ollama")
    || (config.mode === "auto" && status.active_provider === "ollama" && status.provider_ready)
  ) {
    return "ollama";
  }
  if (
    config.mode === "custom"
    || config.mode === "provider"
    || (config.mode === "auto" && (config.has_api_key || (status.provider_ready && status.active_provider !== "ollama")))
  ) {
    return "cloud";
  }
  return "disabled";
}

function initialDraftsFromRag(rag: RagSettingsResponse): RagDrafts {
  const { config, presets, reusable_providers } = rag;
  const uiMode = deriveSavedUiMode(rag);
  const supportedCloud = reusable_providers.filter(
    (item) => item.configured && !item.keyless && item.supports_embedding !== false,
  );
  const matchedLegacyProvider = config.mode === "provider" && config.provider_name
    ? reusable_providers.find((item) => item.name === config.provider_name)
    : undefined;

  let preset = (config.mode === "disabled" || config.mode === "ollama")
    ? (config.saved_custom_preset || config.preset || "siliconflow")
    : (config.preset || "siliconflow");
  let baseUrl = (config.mode === "disabled" || config.mode === "ollama")
    ? (config.saved_custom_base_url || config.base_url || "")
    : (config.base_url || "");
  let model = config.model || "";
  let dim = config.dim ? String(config.dim) : "";

  if (matchedLegacyProvider) {
    const knownPreset = presets.find((p) => p.id === matchedLegacyProvider.preset);
    preset = knownPreset ? knownPreset.id : "custom";
    baseUrl = matchedLegacyProvider.base_url || knownPreset?.base_url || baseUrl;
    model = config.model || matchedLegacyProvider.embedding_models[0]?.id || knownPreset?.default_model || model;
    dim = dim || (knownPreset?.dim ? String(knownPreset.dim) : "");
  } else if (config.mode === "auto" && !config.has_api_key && supportedCloud.length > 0) {
    const first = supportedCloud[0];
    const knownPreset = presets.find((p) => p.id === first.preset);
    preset = knownPreset ? knownPreset.id : "custom";
    baseUrl = first.base_url || knownPreset?.base_url || baseUrl;
    model = first.embedding_models[0]?.id || knownPreset?.default_model || model;
    dim = knownPreset?.dim ? String(knownPreset.dim) : "";
  }

  const activePreset = presets.find((item) => item.id === preset) || presets[0];
  if (activePreset) {
    if (!preset) preset = activePreset.id;
    if (!baseUrl) baseUrl = activePreset.base_url;
    if (!model) model = activePreset.default_model;
    if (!dim && activePreset.dim) dim = String(activePreset.dim);
  }

  return {
    uiMode,
    cloud: {
      preset,
      base_url: baseUrl,
      model,
      api_key: "",
      clear_api_key: false,
      dim,
    },
    ollama: {
      url: config.ollama_url || DEFAULT_OLLAMA_URL,
      model: (config.mode === "provider" && config.provider_name === "ollama" && config.model)
        ? config.model
        : (config.ollama_model || DEFAULT_OLLAMA_MODEL),
    },
  };
}

function draftsToPayload(drafts: RagDrafts, fallbackCloud?: CloudDraft): Record<string, unknown> {
  const cloud = drafts.uiMode === "cloud" ? drafts.cloud : (fallbackCloud || drafts.cloud);
  const dimNumber = Number(cloud.dim);
  if (drafts.uiMode === "disabled") {
    return {
      mode: "disabled",
      provider_name: "",
      preset: "",
      base_url: "",
      model: "",
      api_key: "",
      clear_api_key: false,
      dim: null,
      ollama_url: drafts.ollama.url.trim() || DEFAULT_OLLAMA_URL,
      ollama_model: drafts.ollama.model.trim() || DEFAULT_OLLAMA_MODEL,
    };
  }
  if (drafts.uiMode === "ollama") {
    return {
      mode: "ollama",
      provider_name: "",
      preset: "",
      base_url: "",
      model: "",
      api_key: "",
      clear_api_key: false,
      dim: null,
      ollama_url: drafts.ollama.url.trim() || DEFAULT_OLLAMA_URL,
      ollama_model: drafts.ollama.model.trim() || DEFAULT_OLLAMA_MODEL,
    };
  }
  return {
    mode: "custom",
    provider_name: "",
    preset: cloud.preset,
    base_url: cloud.base_url.trim(),
    model: cloud.model.trim(),
    api_key: cloud.api_key.trim(),
    clear_api_key: cloud.clear_api_key,
    dim: Number.isInteger(dimNumber) && dimNumber > 0 ? dimNumber : null,
    ollama_url: drafts.ollama.url.trim() || DEFAULT_OLLAMA_URL,
    ollama_model: drafts.ollama.model.trim() || DEFAULT_OLLAMA_MODEL,
  };
}

function serverUndoPayload(rag: RagSettingsResponse): Record<string, unknown> {
  const { config } = rag;
  return {
    mode: config.mode,
    provider_name: config.provider_name,
    preset: config.preset,
    base_url: config.base_url,
    model: config.model,
    api_key: "",
    clear_api_key: false,
    dim: config.dim,
    ollama_url: config.ollama_url || DEFAULT_OLLAMA_URL,
    ollama_model: config.ollama_model || DEFAULT_OLLAMA_MODEL,
  };
}

function isDraftDirty(drafts: RagDrafts, baseline: RagDrafts): boolean {
  if (drafts.uiMode !== baseline.uiMode) return true;
  if (drafts.uiMode === "cloud") {
    return (
      drafts.cloud.preset !== baseline.cloud.preset
      || drafts.cloud.base_url.trim().replace(/\/+$/, "") !== baseline.cloud.base_url.trim().replace(/\/+$/, "")
      || drafts.cloud.model.trim() !== baseline.cloud.model.trim()
      || drafts.cloud.dim.trim() !== baseline.cloud.dim.trim()
      || drafts.cloud.api_key.trim().length > 0
      || drafts.cloud.clear_api_key
    );
  }
  if (drafts.uiMode === "ollama") {
    return (
      drafts.ollama.url.trim().replace(/\/+$/, "") !== baseline.ollama.url.trim().replace(/\/+$/, "")
      || drafts.ollama.model.trim() !== baseline.ollama.model.trim()
    );
  }
  return false;
}

/** 设置 · 检索与 RAG：3 选 1 向量配置 + 自动复用密钥与 Ollama 发现 + 后台非阻塞建库 + 召回测试。 */
export function RagSection({
  ragData,
  loadError = "",
  onReload,
  onRagUpdated,
  onOpenModels,
  onStatusInvalidated,
  onDirtyChange,
}: {
  ragData?: RagSettingsResponse | null;
  loadError?: string;
  onReload?: () => void;
  onRagUpdated?: (next: RagSettingsResponse) => void;
  onOpenModels?: () => void;
  onStatusInvalidated?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [localRag, setLocalRag] = useState<RagSettingsResponse | null>(null);
  const rag = ragData !== undefined ? ragData : localRag;
  const [drafts, setDrafts] = useState<RagDrafts | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<"test" | "save" | "save_backfill" | "undo" | "">("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState("");
  const [saveResult, setSaveResult] = useState("");
  const [undoPayload, setUndoPayload] = useState<Record<string, unknown> | null>(null);
  const [confirmRebuildAction, setConfirmRebuildAction] = useState<null | (() => Promise<void>)>(null);
  const [showKeyOverride, setShowKeyOverride] = useState(false);
  const [showPrimer, setShowPrimer] = useState(false);
  const [ollamaProbe, setOllamaProbe] = useState<RagOllamaDiscoveryResponse | null>(null);
  const [ollamaProbing, setOllamaProbing] = useState(false);
  const [copiedPullCmd, setCopiedPullCmd] = useState(false);

  const backfillJob = useRagBackfillStore((state) => state.job);
  const storeLatestRag = useRagBackfillStore((state) => state.latestRag);
  const isBackfilling = backfillJob?.status === "running";
  const lastHydratedSigRef = useRef<string>("");
  const ollamaAttemptedUrlRef = useRef<string>("");

  const applyRag = useCallback((next: RagSettingsResponse, forceHydrate = true) => {
    if (ragData === undefined) setLocalRag(next);
    onRagUpdated?.(next);
    onStatusInvalidated?.();
    if (forceHydrate) {
      setDrafts(initialDraftsFromRag(next));
      setShowKeyOverride(false);
      lastHydratedSigRef.current = JSON.stringify(next.config) + "|" + next.status.effective_mode;
    }
  }, [onRagUpdated, onStatusInvalidated, ragData]);

  const loadStandalone = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await api.ragSettings();
      if (ragData === undefined) setLocalRag(next);
      onRagUpdated?.(next);
      setDrafts(initialDraftsFromRag(next));
      setShowKeyOverride(false);
      lastHydratedSigRef.current = JSON.stringify(next.config) + "|" + next.status.effective_mode;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取检索与 RAG 状态");
    } finally {
      setLoading(false);
    }
  }, [onRagUpdated, ragData]);

  useEffect(() => {
    if (ragData === undefined) {
      void loadStandalone();
    }
  }, [loadStandalone, ragData]);

  useEffect(() => {
    if (!ragData) return;
    setLoading(false);
    const sig = JSON.stringify(ragData.config) + "|" + ragData.status.effective_mode;
    if (lastHydratedSigRef.current !== sig) {
      lastHydratedSigRef.current = sig;
      setDrafts(initialDraftsFromRag(ragData));
      setShowKeyOverride(false);
    }
  }, [ragData]);

  useEffect(() => {
    if (!storeLatestRag || ragData !== undefined) return;
    setLocalRag(storeLatestRag);
  }, [ragData, storeLatestRag]);

  const baselineDrafts = useMemo(() => (rag ? initialDraftsFromRag(rag) : null), [rag]);
  const dirty = Boolean(drafts && baselineDrafts && isDraftDirty(drafts, baselineDrafts));

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => () => {
    onDirtyChange?.(false);
  }, [onDirtyChange]);

  const discoverOllama = useCallback(async (url?: string) => {
    if (typeof api.ragOllamaModels !== "function") return;
    const cleanTarget = (url || DEFAULT_OLLAMA_URL).trim() || DEFAULT_OLLAMA_URL;
    ollamaAttemptedUrlRef.current = cleanTarget;
    setOllamaProbing(true);
    try {
      const res = await api.ragOllamaModels(cleanTarget);
      setOllamaProbe(res);
      if (res.reachable && res.embedding_models.length > 0) {
        setDrafts((current) => {
          if (!current) return current;
          const typed = current.ollama.model.trim();
          const alreadyInstalled = res.models.some((m) => m.name === typed);
          if (!typed || (typed === DEFAULT_OLLAMA_MODEL && !alreadyInstalled)) {
            return {
              ...current,
              ollama: { ...current.ollama, model: res.embedding_models[0] },
            };
          }
          return current;
        });
      }
    } catch {
      setOllamaProbe({
        ok: true,
        reachable: false,
        url: cleanTarget,
        models: [],
        embedding_models: [],
        error: "probe_failed",
      });
    } finally {
      setOllamaProbing(false);
    }
  }, []);

  const currentOllamaUrl = drafts?.ollama.url || DEFAULT_OLLAMA_URL;
  useEffect(() => {
    if (drafts?.uiMode !== "ollama" || ollamaProbing) return;
    const cleanTarget = currentOllamaUrl.trim() || DEFAULT_OLLAMA_URL;
    if (ollamaAttemptedUrlRef.current === cleanTarget && ollamaProbe !== null) return;
    void discoverOllama(cleanTarget);
  }, [currentOllamaUrl, discoverOllama, drafts?.uiMode, ollamaProbe, ollamaProbing]);

  const activePreset = useMemo(() => {
    if (!rag || !drafts) return null;
    return rag.presets.find((item) => item.id === drafts.cloud.preset) || rag.presets[0] || null;
  }, [drafts, rag]);

  const reusableCloudProviders = useMemo(() => {
    if (!rag) return [];
    return rag.reusable_providers.filter((item) => item.configured && !item.keyless && item.supports_embedding !== false);
  }, [rag]);

  const unsupportedConfigured = useMemo(() => {
    if (!rag) return [];
    return rag.reusable_providers.filter((item) => item.configured && item.supports_embedding === false);
  }, [rag]);

  const reusableKeyInfo = useMemo(() => {
    if (!rag || !drafts) return null;
    if (drafts.cloud.clear_api_key || drafts.cloud.api_key.trim()) return null;
    const targetOrigin = originOfUrl(drafts.cloud.base_url);
    if (!targetOrigin) return null;
    const providerMatch = reusableCloudProviders.find((p) => originOfUrl(p.base_url) === targetOrigin);
    if (providerMatch) {
      return {
        kind: "provider" as const,
        hint: `已从「AI 与模型 → ${providerMatch.name}」自动复用 API Key`,
      };
    }
    const savedOrigin = originOfUrl(rag.config.saved_custom_base_url || rag.config.base_url);
    const hasSaved = Boolean(
      (rag.config.has_api_key && rag.config.api_key_source === "saved")
      || rag.config.has_saved_custom_key,
    );
    if (hasSaved && savedOrigin === targetOrigin) {
      return {
        kind: "saved" as const,
        hint: "已保存该接口的专用 API Key，无需重复输入",
      };
    }
    if (rag.config.has_api_key && rag.config.api_key_source === "env" && originOfUrl(rag.config.base_url) === targetOrigin) {
      return {
        kind: "env" as const,
        hint: `已检测到环境变量密钥（${activePreset?.api_key_env || "ENV"}）`,
      };
    }
    return null;
  }, [activePreset?.api_key_env, drafts, rag, reusableCloudProviders]);

  const cloudQuickModels = useMemo(() => {
    const out: string[] = [];
    const seen = new Set<string>();
    const add = (id: string) => {
      const clean = id.trim();
      if (!clean || seen.has(clean)) return;
      seen.add(clean);
      out.push(clean);
    };
    if (drafts) {
      const targetOrigin = originOfUrl(drafts.cloud.base_url);
      for (const p of rag?.reusable_providers || []) {
        if (originOfUrl(p.base_url) === targetOrigin) {
          for (const m of p.embedding_models || []) add(m.id);
        }
      }
    }
    for (const m of activePreset?.suggested_models || []) add(m);
    return out;
  }, [activePreset?.suggested_models, drafts, rag?.reusable_providers]);

  function updateCloud(patch: Partial<CloudDraft>) {
    setDrafts((current) => current && {
      ...current,
      cloud: { ...current.cloud, ...patch },
    });
    setTestResult("");
    setSaveResult("");
    setError("");
  }

  function selectCloudPreset(presetId: string) {
    if (!rag) return;
    const target = rag.presets.find((item) => item.id === presetId);
    if (!target) return;
    setShowKeyOverride(false);
    updateCloud({
      preset: target.id,
      base_url: target.base_url || (target.id === "custom" ? drafts?.cloud.base_url || "" : ""),
      model: target.default_model || "",
      dim: target.dim ? String(target.dim) : "",
      clear_api_key: false,
    });
  }

  async function runTestOnly() {
    if (!drafts || busyAction || drafts.uiMode === "disabled") return;
    setBusyAction("test");
    setError("");
    setTestResult("");
    try {
      const probe = await api.testRagEmbedding(draftsToPayload(drafts));
      const nextCloudPatch: Partial<CloudDraft> = {};
      if (drafts.uiMode === "cloud") {
        if (probe.url_normalized && probe.normalized_base_url) {
          nextCloudPatch.base_url = probe.normalized_base_url;
        }
        if (!drafts.cloud.dim.trim() && probe.dim) {
          nextCloudPatch.dim = String(probe.dim);
        }
        if (Object.keys(nextCloudPatch).length > 0) {
          setDrafts((curr) => curr && { ...curr, cloud: { ...curr.cloud, ...nextCloudPatch } });
        }
      }
      setTestResult(
        `连接成功 · ${probe.model} · ${probe.dim} 维 · ${probe.latency_ms}ms${probe.url_normalized ? "（已自动清理接口后缀）" : ""}`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "向量模型测试失败");
    } finally {
      setBusyAction("");
    }
  }

  async function executeSaveAndOptionalBackfill(withBackfill: boolean, rebuildCollection: boolean) {
    if (!rag || !drafts || busyAction) return;
    setBusyAction(withBackfill ? "save_backfill" : "save");
    setError("");
    setSaveResult("");
    setTestResult("");
    try {
      let effectiveDrafts = drafts;
      const clearingWithoutReplacement =
        drafts.uiMode === "cloud" && drafts.cloud.clear_api_key && !drafts.cloud.api_key.trim();

      if (drafts.uiMode !== "disabled" && !clearingWithoutReplacement) {
        const probe = await api.testRagEmbedding(draftsToPayload(drafts));
        const nextCloud = { ...drafts.cloud };
        if (drafts.uiMode === "cloud") {
          if (probe.url_normalized && probe.normalized_base_url) {
            nextCloud.base_url = probe.normalized_base_url;
          }
          if (!nextCloud.dim.trim() && probe.dim) {
            nextCloud.dim = String(probe.dim);
          }
        }
        effectiveDrafts = { ...drafts, cloud: nextCloud };
        setTestResult(
          `连通性通过 · ${probe.model} · ${probe.dim} 维 · ${probe.latency_ms}ms`,
        );
      }

      const previousSnapshot = serverUndoPayload(rag);
      const updated = await api.saveRagSettings(draftsToPayload(effectiveDrafts));
      setUndoPayload(previousSnapshot);
      applyRag(updated, true);

      const shouldRunBackfill = Boolean(
        withBackfill
        && effectiveDrafts.uiMode !== "disabled"
        && !clearingWithoutReplacement
        && updated.status.knowledge_ready
        && updated.status.vector_stats.documents > 0
        && (
          rebuildCollection
          || updated.status.needs_rebuild
          || updated.status.needs_backfill
          || updated.status.vector_stats.vector_indexed === 0
        ),
      );
      if (shouldRunBackfill) {
        await useRagBackfillStore.getState().start(
          Boolean(rebuildCollection || updated.status.needs_rebuild),
        );
        setSaveResult("配置已保存，后台向量索引已启动。");
      } else {
        setSaveResult(
          effectiveDrafts.uiMode === "disabled"
            ? "已切换为仅关键词检索。"
            : "向量模型配置已保存。",
        );
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存向量配置失败");
    } finally {
      setBusyAction("");
    }
  }

  async function saveWithoutTest() {
    if (!rag || !drafts || busyAction) return;
    setBusyAction("save");
    setError("");
    setSaveResult("");
    try {
      const previousSnapshot = serverUndoPayload(rag);
      const updated = await api.saveRagSettings(draftsToPayload(drafts));
      setUndoPayload(previousSnapshot);
      applyRag(updated, true);
      setSaveResult("配置已保存（未执行连通性测试）。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存向量配置失败");
    } finally {
      setBusyAction("");
    }
  }

  async function handleUndoSave() {
    if (!undoPayload || busyAction) return;
    setBusyAction("undo");
    setError("");
    try {
      const reverted = await api.saveRagSettings(undoPayload);
      setUndoPayload(null);
      applyRag(reverted, true);
      setSaveResult("已撤销刚才的更改，恢复为上一版配置。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "撤销更改失败");
    } finally {
      setBusyAction("");
    }
  }

  async function startManualBackfill(rebuild: boolean) {
    setError("");
    setSaveResult("");
    try {
      await useRagBackfillStore.getState().start(rebuild);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "启动向量索引失败");
    }
  }

  async function copyPullCommand() {
    if (!drafts) return;
    const cmd = `ollama pull ${drafts.ollama.model.trim() || DEFAULT_OLLAMA_MODEL}`;
    try {
      await navigator.clipboard?.writeText(cmd);
      setCopiedPullCmd(true);
      window.setTimeout(() => setCopiedPullCmd(false), 1800);
    } catch {
      setCopiedPullCmd(false);
    }
  }

  const displayError = error || loadError;
  if (loading && !rag && !loadError) {
    return <p className="settings-empty">正在读取检索能力与向量配置…</p>;
  }
  if (!rag || !drafts) {
    return (
      <SettingsSection title="检索与 RAG" description="检查知识库向量索引和模型可用性。">
        {displayError && <div className="settings-error">{displayError}</div>}
        <button className="quiet-button" type="button" onClick={() => (onReload ? onReload() : void loadStandalone())}>重新读取</button>
      </SettingsSection>
    );
  }

  const { status } = rag;
  const stats = status.vector_stats;
  const badge = formatRetrievalBadge(rag);
  const totalDocs = stats.documents || 0;
  const indexedDocs = stats.vector_indexed || 0;
  const missingDocs = Math.max(0, totalDocs - indexedDocs);
  const coveragePct = totalDocs > 0 ? Math.min(100, Math.round((indexedDocs / totalDocs) * 100)) : 0;

  const targetModelName = drafts.uiMode === "cloud"
    ? drafts.cloud.model.trim()
    : drafts.uiMode === "ollama"
      ? drafts.ollama.model.trim()
      : "";
  const storedModelName = status.stored_signature?.model || "";
  const modelSwitchingReplacesVectors = Boolean(
    drafts.uiMode !== "disabled"
    && status.knowledge_ready
    && totalDocs > 0
    && indexedDocs > 0
    && ((storedModelName && targetModelName && storedModelName !== targetModelName) || status.signature_mismatch),
  );
  const clearingWithoutNewKey = Boolean(
    drafts.uiMode === "cloud" && drafts.cloud.clear_api_key && !drafts.cloud.api_key.trim(),
  );

  function handlePrimarySubmit() {
    if (!dirty || busyAction) return;
    if (drafts!.uiMode === "disabled") {
      void executeSaveAndOptionalBackfill(false, false);
      return;
    }
    if (clearingWithoutNewKey) {
      void saveWithoutTest();
      return;
    }
    const wantsBackfill = Boolean(status.knowledge_ready && totalDocs > 0);
    if (modelSwitchingReplacesVectors) {
      setConfirmRebuildAction(() => () => executeSaveAndOptionalBackfill(true, true));
      return;
    }
    void executeSaveAndOptionalBackfill(wantsBackfill, false);
  }

  let primaryLabel = "当前配置已生效";
  if (dirty) {
    if (drafts.uiMode === "disabled" || clearingWithoutNewKey) {
      primaryLabel = busyAction === "save" ? "正在保存…" : "保存配置";
    } else if (modelSwitchingReplacesVectors) {
      primaryLabel = busyAction === "save_backfill" ? "正在校验并启动…" : "测试并保存，后台重建向量";
    } else if (status.knowledge_ready && totalDocs > 0 && (missingDocs > 0 || indexedDocs === 0)) {
      primaryLabel = busyAction === "save_backfill"
        ? "正在校验并启动…"
        : `测试并保存，补建 ${missingDocs || totalDocs} 份向量`;
    } else {
      primaryLabel = busyAction === "save" ? "正在校验并保存…" : "测试并保存";
    }
  }

  const primerVisible = status.effective_mode !== "hybrid" && rag.config.mode !== "disabled";
  const jobDone = backfillJob?.done ?? 0;
  const jobTotal = Math.max(1, backfillJob?.total ?? totalDocs);
  const jobPct = Math.min(100, Math.round((jobDone / jobTotal) * 100));

  return (
    <>
      <SettingsSection
        title="当前检索能力"
        description="实时读取当前资料库的真实索引与向量可用性，不写回任何伪状态。"
      >
        <div className="rag-status-banner" data-tone={badge.tone}>
          <div className="rag-status-icon">
            {badge.tone === "ready" ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
          </div>
          <div className="rag-status-copy">
            <strong>{status.semantic_status.title}</strong>
            <p>{status.semantic_status.detail}</p>
            {status.semantic_status.action && <small>建议：{status.semantic_status.action}</small>}
          </div>
          {!isBackfilling && status.needs_rebuild && (
            <button
              className="primary-button"
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => setConfirmRebuildAction(() => () => startManualBackfill(true))}
            >
              <RefreshCw size={14} />
              重建向量索引（{totalDocs} 份）
            </button>
          )}
          {!isBackfilling && !status.needs_rebuild && status.needs_backfill && (
            <button
              className="primary-button"
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => void startManualBackfill(false)}
            >
              <Database size={14} />
              补建 {stats.vector_pending + stats.vector_error} 份向量
            </button>
          )}
        </div>

        {isBackfilling && backfillJob && (
          <div className="rag-backfill-bar">
            <div className="rag-backfill-head">
              <strong>
                {backfillJob.rebuild ? "正在后台重建向量索引" : "正在后台补建向量"} · {jobDone}/{jobTotal} 份（{jobPct}%）
              </strong>
              <button
                className="quiet-button"
                type="button"
                disabled={Boolean(backfillJob.cancel_requested)}
                onClick={() => void useRagBackfillStore.getState().cancel()}
              >
                <Square size={12} />
                {backfillJob.cancel_requested ? "正在停止…" : "停止"}
              </button>
            </div>
            <div className="rag-progress-track">
              <div className="rag-progress-fill" style={{ width: `${jobPct}%` }} />
            </div>
            {backfillJob.current_title && (
              <small>正在处理：{backfillJob.current_title}</small>
            )}
          </div>
        )}

        <div className="rag-metrics">
          <div>
            <span>检索模式</span>
            <strong>{formatEffectiveModeLabel(status.effective_mode)}</strong>
          </div>
          <div>
            <span>当前向量模型</span>
            <strong>
              {status.active_model
                ? `${status.display_provider || status.active_provider} · ${status.active_model}${status.active_dim ? ` · ${status.active_dim} 维` : ""}`
                : "未启用"}
            </strong>
          </div>
          <div>
            <span>向量覆盖</span>
            <strong>
              {status.knowledge_ready
                ? `${indexedDocs} / ${totalDocs} 份（${coveragePct}%）`
                : "未导入资料"}
            </strong>
            {status.knowledge_ready && totalDocs > 0 && (
              <div className="rag-progress-track">
                <div className="rag-progress-fill" style={{ width: `${coveragePct}%` }} />
              </div>
            )}
          </div>
        </div>

        {status.error_samples.length > 0 && (
          <div className="rag-error-list">
            <strong>最近向量化失败示例（可修复配置后点击上方补建）</strong>
            {status.error_samples.map((sample) => (
              <div key={sample.source}>
                <span>{sample.title}</span>
                <small>{sample.error}</small>
              </div>
            ))}
          </div>
        )}

        {(primerVisible || showPrimer) && (
          <div className="rag-role-primer">
            <div>
              <strong>对话模型（写回答 · AI 与模型）</strong>
              <p>负责读参考资料、总结与出题。DeepSeek、MiniMax 等只提供对话接口，官方不带资料向量化能力。</p>
            </div>
            <div>
              <strong>向量模型（找片段 · 本页配置）</strong>
              <p>把每段资料压缩成语义向量，实现“意思相近也能找到”。关闭或未配置时仍可精确关键词检索。</p>
            </div>
          </div>
        )}
        {!primerVisible && (
          <button
            type="button"
            className="rag-primer-toggle"
            onClick={() => setShowPrimer((prev) => !prev)}
          >
            {showPrimer ? "收起：对话模型与向量模型有什么区别" : "了解：对话模型与向量模型有什么区别"}
          </button>
        )}
      </SettingsSection>

      <SettingsSection
        title="向量模型配置"
        description="按需选择检索方式；云端向量与本地 Ollama 互不影响，切换模式会保留各自已填写的参数。"
      >
        <div className="rag-mode-cards" role="radiogroup" aria-label="向量检索方式">
          <label className="rag-mode-card" data-selected={drafts.uiMode === "disabled"}>
            <input
              type="radio"
              name="rag-ui-mode"
              value="disabled"
              checked={drafts.uiMode === "disabled"}
              onChange={() => {
                setDrafts({ ...drafts, uiMode: "disabled" });
                setTestResult("");
                setError("");
              }}
            />
            <div>
              <strong>仅关键词检索</strong>
              <small>本地 SQLite FTS5，零 API 成本，不向外部发送资料内容</small>
            </div>
          </label>

          <label className="rag-mode-card" data-selected={drafts.uiMode === "cloud"}>
            <input
              type="radio"
              name="rag-ui-mode"
              value="cloud"
              checked={drafts.uiMode === "cloud"}
              onChange={() => {
                setDrafts({ ...drafts, uiMode: "cloud" });
                setTestResult("");
                setError("");
              }}
            />
            <div>
              <strong>
                云端向量模型
                <span className="rag-mode-card-tag">
                  {reusableCloudProviders.length > 0
                    ? `可复用 ${reusableCloudProviders[0].name} 密钥`
                    : "推荐 · BGE-M3 免费可用"}
                </span>
              </strong>
              <small>使用硅基流动 / 阿里云百炼 / 智谱 / OpenAI 或兼容网关，语义召回最准确</small>
            </div>
          </label>

          <label className="rag-mode-card" data-selected={drafts.uiMode === "ollama"}>
            <input
              type="radio"
              name="rag-ui-mode"
              value="ollama"
              checked={drafts.uiMode === "ollama"}
              onChange={() => {
                setDrafts({ ...drafts, uiMode: "ollama" });
                setTestResult("");
                setError("");
              }}
            />
            <div>
              <strong>本地 Ollama</strong>
              <small>全部计算在自己电脑完成，离线与隐私首选</small>
            </div>
          </label>
        </div>

        {drafts.uiMode === "cloud" && (
          <>
            <div className="rag-preset-grid">
              {rag.presets.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  className="rag-preset-card"
                  data-selected={drafts.cloud.preset === preset.id}
                  onClick={() => selectCloudPreset(preset.id)}
                >
                  <strong>{preset.label}</strong>
                  <small>{preset.badge}</small>
                </button>
              ))}
            </div>

            {activePreset && (
              <p className="settings-model-hint">{activePreset.description}</p>
            )}

            {!reusableKeyInfo && unsupportedConfigured.length > 0 && status.effective_mode !== "hybrid" && (
              <p className="settings-model-hint">
                提示：你配置的 {unsupportedConfigured.map((p) => p.name).join(" / ")} 仅支持对话生成，请从上方选一个向量平台。
              </p>
            )}

            {drafts.cloud.preset === "custom" && (
              <label className="settings-field">
                <span>接口地址（base_url，填写根路径）</span>
                <input
                  value={drafts.cloud.base_url}
                  placeholder="https://example.com/v1"
                  onChange={(event) => updateCloud({ base_url: event.target.value })}
                />
              </label>
            )}

            <label className="settings-field">
              <span>向量模型 ID</span>
              <input
                value={drafts.cloud.model}
                placeholder={activePreset?.default_model || "如 BAAI/bge-m3"}
                onChange={(event) => updateCloud({ model: event.target.value })}
              />
            </label>

            {cloudQuickModels.length > 0 && (
              <div className="rag-chip-row">
                <span>常用推荐：</span>
                {cloudQuickModels.map((modelId) => (
                  <button
                    key={modelId}
                    type="button"
                    className="rag-chip"
                    data-active={drafts.cloud.model.trim() === modelId}
                    onClick={() => updateCloud({ model: modelId })}
                  >
                    {modelId}
                  </button>
                ))}
              </div>
            )}

            {reusableKeyInfo && !showKeyOverride ? (
              <div className="rag-key-reused">
                <KeyRound size={15} />
                <span>{reusableKeyInfo.hint}</span>
                <div className="rag-inline-actions">
                  <button
                    type="button"
                    className="quiet-button"
                    onClick={() => setShowKeyOverride(true)}
                  >
                    改用其它密钥
                  </button>
                  {reusableKeyInfo.kind === "saved" && (
                    <button
                      type="button"
                      className="quiet-button danger"
                      aria-pressed={drafts.cloud.clear_api_key}
                      onClick={() => updateCloud({ clear_api_key: !drafts.cloud.clear_api_key, api_key: "" })}
                    >
                      {drafts.cloud.clear_api_key ? "将清除已存密钥（点此取消）" : "清除已存密钥"}
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="settings-field">
                <span>API Key（仅保存在本地应用数据目录）</span>
                <input
                  type="password"
                  value={drafts.cloud.api_key}
                  autoComplete="off"
                  placeholder={
                    drafts.cloud.clear_api_key
                      ? "已选择清除已存密钥，可直接保存或输入新密钥"
                      : "粘贴该平台的 API Key（sk-...）"
                  }
                  onChange={(event) => updateCloud({ api_key: event.target.value, clear_api_key: false })}
                />
                <div className="rag-inline-actions">
                  {showKeyOverride && (
                    <button
                      type="button"
                      className="quiet-button"
                      onClick={() => {
                        setShowKeyOverride(false);
                        updateCloud({ api_key: "" });
                      }}
                    >
                      改回自动复用
                    </button>
                  )}
                  {(rag.config.has_saved_custom_key || drafts.cloud.clear_api_key) && !reusableKeyInfo && (
                    <button
                      type="button"
                      className="quiet-button danger"
                      aria-pressed={drafts.cloud.clear_api_key}
                      onClick={() => updateCloud({ clear_api_key: !drafts.cloud.clear_api_key, api_key: "" })}
                    >
                      {drafts.cloud.clear_api_key ? "将清除已存密钥（点此取消）" : "清除已存密钥"}
                    </button>
                  )}
                  {onOpenModels && (
                    <button className="quiet-button" type="button" onClick={onOpenModels}>
                      去「AI 与模型」管理供应商 →
                    </button>
                  )}
                </div>
              </div>
            )}

            <details className="rag-advanced">
              <summary>高级选项（接口地址与向量维度）</summary>
              {drafts.cloud.preset !== "custom" && (
                <label className="settings-field">
                  <span>接口地址（仅私有代理或自定义网关需要改动）</span>
                  <input
                    value={drafts.cloud.base_url}
                    placeholder="https://api.example.com/v1"
                    onChange={(event) => updateCloud({ base_url: event.target.value })}
                  />
                </label>
              )}
              <label className="settings-field">
                <span>向量维度（dim，留空将在测试时自动识别）</span>
                <input
                  type="number"
                  min={1}
                  max={16384}
                  value={drafts.cloud.dim}
                  placeholder="留空自动探测"
                  onChange={(event) => updateCloud({ dim: event.target.value })}
                />
              </label>
            </details>
          </>
        )}

        {drafts.uiMode === "ollama" && (
          <div className="rag-ollama-box">
            <div className="rag-inline-actions">
              <button
                className="quiet-button"
                type="button"
                disabled={ollamaProbing}
                onClick={() => void discoverOllama(drafts.ollama.url)}
              >
                <RefreshCw size={13} className={ollamaProbing ? "spin" : ""} />
                {ollamaProbing ? "正在检测本地 Ollama…" : "重新检测本机模型"}
              </button>
              {ollamaProbe && (
                <small className="settings-model-hint">
                  {ollamaProbe.reachable
                    ? ollamaProbe.embedding_models.length > 0
                      ? `已发现 ${ollamaProbe.embedding_models.length} 个已安装的向量模型`
                      : "Ollama 已运行，但暂未发现向量模型"
                    : `未检测到本地 Ollama（${ollamaProbe.url}）`}
                </small>
              )}
            </div>

            {ollamaProbe?.reachable && ollamaProbe.embedding_models.length > 0 ? (
              <div className="rag-chip-row">
                <span>本机已安装：</span>
                {ollamaProbe.models
                  .filter((item) => item.is_embedding)
                  .map((item) => (
                    <button
                      key={item.name}
                      type="button"
                      className="rag-chip"
                      data-active={drafts.ollama.model.trim() === item.name}
                      onClick={() => setDrafts({ ...drafts, ollama: { ...drafts.ollama, model: item.name } })}
                    >
                      {item.name}
                      {item.size_label ? ` · ${item.size_label}` : ""}
                    </button>
                  ))}
              </div>
            ) : (
              <>
                <div className="rag-chip-row">
                  <span>推荐模型：</span>
                  {RECOMMENDED_OLLAMA_MODELS.map((modelId) => (
                    <button
                      key={modelId}
                      type="button"
                      className="rag-chip"
                      data-active={drafts.ollama.model.trim() === modelId}
                      onClick={() => setDrafts({ ...drafts, ollama: { ...drafts.ollama, model: modelId } })}
                    >
                      {modelId}
                    </button>
                  ))}
                </div>
                <div className="rag-ollama-cmd">
                  <code>ollama pull {drafts.ollama.model.trim() || DEFAULT_OLLAMA_MODEL}</code>
                  <button className="quiet-button" type="button" onClick={() => void copyPullCommand()}>
                    <Copy size={13} />
                    {copiedPullCmd ? "已复制 ✓" : "复制安装命令"}
                  </button>
                </div>
              </>
            )}

            <label className="settings-field">
              <span>本地模型名称</span>
              <input
                value={drafts.ollama.model}
                placeholder={DEFAULT_OLLAMA_MODEL}
                onChange={(event) => {
                  setDrafts({ ...drafts, ollama: { ...drafts.ollama, model: event.target.value } });
                  setTestResult("");
                }}
              />
            </label>

            <details className="rag-advanced">
              <summary>高级选项（Ollama 服务地址）</summary>
              <label className="settings-field">
                <span>服务地址（默认 http://localhost:11434）</span>
                <input
                  value={drafts.ollama.url}
                  placeholder={DEFAULT_OLLAMA_URL}
                  onChange={(event) => {
                    setDrafts({ ...drafts, ollama: { ...drafts.ollama, url: event.target.value } });
                    setTestResult("");
                  }}
                />
              </label>
            </details>
          </div>
        )}

        {testResult && <div className="rag-feedback" data-tone="ready">{testResult}</div>}
        {saveResult && (
          <div className="rag-feedback" data-tone="ready">
            <span>{saveResult}</span>
            {undoPayload && (
              <button
                type="button"
                className="quiet-button"
                disabled={Boolean(busyAction)}
                onClick={() => void handleUndoSave()}
              >
                撤销更改
              </button>
            )}
          </div>
        )}
        {error && <div className="rag-feedback" data-tone="warn">{error}</div>}

        <div className="rag-inline-actions">
          <button
            className="primary-button"
            type="button"
            disabled={!dirty || Boolean(busyAction)}
            onClick={handlePrimarySubmit}
          >
            <Check size={14} />
            {primaryLabel}
          </button>

          {drafts.uiMode !== "disabled" && (
            <button
              className="quiet-button"
              type="button"
              disabled={Boolean(busyAction) || clearingWithoutNewKey}
              onClick={() => void runTestOnly()}
            >
              <Sparkles size={14} />
              {busyAction === "test" ? "正在测试…" : "仅测试连通性"}
            </button>
          )}

          {dirty && drafts.uiMode !== "disabled" && !clearingWithoutNewKey && status.knowledge_ready && totalDocs > 0 && (
            <button
              className="quiet-button"
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => void saveWithoutTest()}
            >
              仅保存
            </button>
          )}

          {dirty && baselineDrafts && (
            <button
              className="quiet-button"
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => {
                setDrafts(baselineDrafts);
                setShowKeyOverride(false);
                setError("");
                setTestResult("");
              }}
            >
              还原修改
            </button>
          )}
        </div>
      </SettingsSection>

      <RagSearchTestCard
        knowledgeReady={status.knowledge_ready}
        sampleQueries={status.sample_queries}
      />

      <details className="rag-footnote">
        <summary>术语与检索机制（点击展开说明）</summary>
        <dl className="rag-glossary">
          <div>
            <dt>混合检索（hybrid）</dt>
            <dd>同时使用向量语义召回与 SQLite FTS5 关键词全文检索，再通过 RRF 融合排序，兼顾“搜意思”和“搜原词”。</dd>
          </div>
          <div>
            <dt>仅关键词（fts_only）</dt>
            <dd>当前只有 SQLite FTS5（含中文 2-gram）参与搜索；不调用外部向量服务，回答会在顶部明确标注。</dd>
          </div>
          <div>
            <dt>目录直查（directory / grep）</dt>
            <dd>直接按资料目录结构与文件名定位文档段落，不依赖向量模型。</dd>
          </div>
        </dl>
      </details>

      {confirmRebuildAction && (
        <ConfirmDialog
          busy={Boolean(busyAction)}
          title="更换模型并重建向量索引？"
          detail={`当前资料库已有 ${indexedDocs} 份向量${storedModelName ? `（使用「${storedModelName}」）` : ""}。继续后将在后台清空旧向量并以新模型重新生成（共 ${totalDocs} 份资料），期间仍可正常使用关键词检索。`}
          confirmLabel="确认并后台重建"
          onCancel={() => setConfirmRebuildAction(null)}
          onConfirm={() => {
            const action = confirmRebuildAction;
            setConfirmRebuildAction(null);
            void action();
          }}
        />
      )}
    </>
  );
}
