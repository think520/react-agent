import { useEffect, useState } from "react";
import { Search } from "lucide-react";

import { api } from "../../../lib/api";
import type { RagSettingsResponse, SettingsSummary, UserPreferences } from "../../../types";
import { DropdownSelect } from "../../DropdownSelect";
import { ModelSelect } from "../../ModelSelect";
import { SettingsRow, SettingsSection, SettingsSegmented, SettingsToggle } from "../SettingsPrimitives";
import { ProvidersPane } from "../providers/ProvidersPane";

type Usage = Awaited<ReturnType<typeof api.llmUsage>>;

/**
 * 设置 · AI 与模型（2026-10-17 S3）。
 * 供应商从嵌套弹窗改为**节内主从**（ProvidersPane），右侧详情常驻；
 * 模型/任务、用量台账、联网资料各一张卡；补齐语义向量模型分工直达。
 */
export function ModelsSection({ settings, preferences, usage, usageDays, setUsageDays, patch, searchTest, testSearchProvider, onSettingsChange, onOpenRag }: {
  settings: SettingsSummary;
  preferences: UserPreferences;
  usage: Usage | null;
  usageDays: 7 | 30;
  setUsageDays: (value: 7 | 30) => void;
  patch: (patch: Record<string, unknown>) => void;
  searchTest: Record<string, string>;
  testSearchProvider: (name: "auto" | "tavily" | "exa") => void;
  onSettingsChange: (settings: SettingsSummary) => void;
  onOpenRag?: () => void;
}) {
  const [rag, setRag] = useState<RagSettingsResponse | null>(null);

  useEffect(() => {
    void api.ragSettings?.().then(setRag).catch(() => setRag(null));
  }, [settings.providers]);

  const ragBadge = !rag
    ? { tone: "muted", label: "读取中" }
    : rag.status.effective_mode === "hybrid"
      ? { tone: "ready", label: "hybrid 就绪" }
      : rag.status.needs_rebuild
        ? { tone: "warn", label: "待重建向量" }
        : rag.status.embedding_available && rag.status.needs_backfill
          ? { tone: "warn", label: "待建向量" }
          : rag.status.provider_ready && rag.status.vector_stats.documents === 0
            ? { tone: "muted", label: "待导入资料" }
            : { tone: "muted", label: "仅纯文本" };

  const ragHint = !rag
    ? "用于资料库按意思搜索；支持复用硅基流动 / 百炼 / 智谱 / OpenAI 或本地 Ollama"
    : rag.status.effective_mode === "hybrid"
      ? `已启用：${rag.status.display_provider || rag.status.active_provider} · ${rag.status.active_model}`
      : rag.status.needs_rebuild
        ? "已切换向量模型，需在「检索与 RAG」重建向量索引后恢复语义检索"
        : rag.status.embedding_available && rag.status.needs_backfill
          ? `模型已就绪（${rag.status.display_provider || rag.status.active_provider} · ${rag.status.active_model}），还需在「检索与 RAG」为已有资料建向量`
          : rag.status.provider_ready && rag.status.vector_stats.documents === 0
            ? `模型已就绪（${rag.status.display_provider || rag.status.active_provider} · ${rag.status.active_model}），导入资料后将自动建立向量`
            : "未启用（当前仅走纯文本检索；DeepSeek/MiniMax 为对话模型，不参与资料向量化）";

  return <>
    <SettingsSection title="供应商" description="这里管理的密钥主要用于聊天与 Wiki 整理；其中支持向量接口的平台（如硅基流动、百炼、智谱、OpenAI），密钥可直接被「检索与 RAG」复用。密钥仅保存在本地应用数据目录。">
      <ProvidersPane
        providers={settings.providers}
        onChanged={async () => { onSettingsChange(await api.settings()); }}
      />
    </SettingsSection>

    <SettingsSection title="模型与任务" description="不同岗位需要不同种类的模型：对话与 Wiki 整理用聊天模型，资料语义召回用向量模型。">
      <SettingsRow label="默认模型" hint="聊天与未指定任务默认使用（仅列对话模型）">
        <ModelSelect providers={settings.providers} kind="chat" label="默认模型" value={preferences.ai.default_provider || "default"} onChange={(value) => patch({ ai: { default_provider: value } })} includeDefault={false} bordered />
      </SettingsRow>
      <SettingsRow label="主题发现模型">
        <ModelSelect providers={settings.providers} kind="chat" label="主题发现模型" value={preferences.ai.task_providers?.wiki_discovery || "default"} onChange={(value) => patch({ ai: { task_providers: { wiki_discovery: value } } })} includeDefault bordered />
      </SettingsRow>
      <SettingsRow label="页面撰写模型">
        <ModelSelect providers={settings.providers} kind="chat" label="页面撰写模型" value={preferences.ai.task_providers?.wiki_drafting || "default"} onChange={(value) => patch({ ai: { task_providers: { wiki_drafting: value } } })} includeDefault bordered />
      </SettingsRow>
      <SettingsRow label="语义向量模型" hint={ragHint}>
        <div className="models-rag-row">
          <span className="rag-mode-badge" data-tone={ragBadge.tone}>
            {ragBadge.label}
          </span>
          {onOpenRag && (
            <button className="quiet-button" type="button" onClick={onOpenRag}>
              配置向量模型 →
            </button>
          )}
        </div>
      </SettingsRow>
      <SettingsRow label="默认整理方式" hint="达到额度后任务会保存并暂停">
        <DropdownSelect className="bordered" ariaLabel="默认整理方式" value={preferences.wiki?.default_mode || "standard"} onChange={(value) => patch({ wiki: { default_mode: value } })} options={[{ value: "catalog", label: "快速建档" }, { value: "standard", label: "标准整理 · 每批 5 份" }, { value: "deep", label: "深度全库" }]} />
      </SettingsRow>
      <div className="settings-model-budget">
        <label><span>请求上限</span><input type="number" min={1} max={500} value={preferences.wiki?.budget.max_requests || 24} onChange={(event) => patch({ wiki: { budget: { max_requests: Number(event.target.value) } } })} /></label>
        <label><span>输入 Token</span><input type="number" min={1000} step={10000} value={preferences.wiki?.budget.max_input_tokens || 300000} onChange={(event) => patch({ wiki: { budget: { max_input_tokens: Number(event.target.value) } } })} /></label>
        <label><span>输出 Token</span><input type="number" min={1000} step={1000} value={preferences.wiki?.budget.max_output_tokens || 40000} onChange={(event) => patch({ wiki: { budget: { max_output_tokens: Number(event.target.value) } } })} /></label>
      </div>
    </SettingsSection>

    <SettingsSection title="AI 用量" description="只记录请求元数据，不保存提示词或资料正文。" footer={<SettingsSegmented label="用量统计范围" value={usageDays} onChange={setUsageDays} options={[{ value: 7, label: "7 天" }, { value: 30, label: "30 天" }]} />}>
      {usage ? <>
        <div className="usage-summary">
          <div><strong>{usage.requests}</strong><span>请求</span></div>
          <div><strong>{usage.input_tokens.toLocaleString()}</strong><span>输入 Token</span></div>
          <div><strong>{usage.output_tokens.toLocaleString()}</strong><span>输出 Token</span></div>
          <div><strong>{usage.cache_reported ? usage.cache_read_tokens.toLocaleString() : "未报告"}</strong><span>缓存读取</span></div>
          <div><strong>{usage.cache_reported ? usage.cache_miss_tokens.toLocaleString() : "未报告"}</strong><span>未缓存 Token</span></div>
          <div><strong>{usage.errors}</strong><span>错误</span></div>
        </div>
        <p className="usage-detail">模型分布：{Object.entries(usage.model_distribution).map(([model, count]) => model + " " + count).join(" · ") || "暂无"}{usage.cost_reported ? " · 已报告费用 $" + usage.cost_usd.toFixed(4) : " · Provider 未报告费用"}</p>
      </> : <p className="settings-empty">还没有可显示的用量记录。</p>}
    </SettingsSection>

    <SettingsSection title="联网资料" description="模型自动模式会在本地资料不足或需要最新信息时搜索；所有模式都保留来源和证据快照。">
      <SettingsRow label="联网权限" hint={preferences.search.permission === "auto" ? "搜索查询可能在模型判断需要时发送给外部搜索服务" : "模型先说明资料缺口，由你确认后才联网"}>
        <SettingsSegmented label="联网权限" value={preferences.search.permission} onChange={(value) => patch({ search: { permission: value } })} options={[{ value: "ask", label: "每次询问" }, { value: "auto", label: "模型自动" }]} />
      </SettingsRow>
      {settings.search_providers.map((provider) => (
        <div className="settings-provider-row" key={provider.name}>
          <span className={"provider-mark " + (provider.configured ? "ready" : "")}><Search size={15} /></span>
          <div><strong>{provider.name === "auto" ? "自动选择" : provider.name === "tavily" ? "Tavily" : "Exa"}</strong><small>{provider.name === "auto" ? "Tavily → Exa" : provider.name === "tavily" ? "需要本地环境变量" : "公共 MCP 搜索"}{searchTest[provider.name] ? " · " + searchTest[provider.name] : ""}</small></div>
          <label><input type="radio" name="search-provider" checked={preferences.search.provider === provider.name} disabled={!provider.configured} onChange={() => patch({ search: { provider: provider.name } })} />默认</label>
          <button className="quiet-button" type="button" disabled={!provider.configured} onClick={() => testSearchProvider(provider.name)}>测试搜索</button>
        </div>
      ))}
      <SettingsRow label="Jina Reader 后备" hint="直接读取失败时使用，并在来源中明确标注">
        <SettingsToggle label="Jina Reader 后备" checked={preferences.search.jina_fallback} onChange={(value) => patch({ search: { jina_fallback: value } })} />
      </SettingsRow>
    </SettingsSection>
  </>;
}
