import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, Bot, BookOpenText, Brain, Check, ChevronLeft, CircleUserRound,
  Cpu, Database, Gauge, RefreshCw, Search, Settings2, ShieldCheck, Sparkles, Wrench, X,
} from "lucide-react";

import { api } from "../lib/api";
import type { LibrarySummary, RuntimeStatus, SettingsSummary, UserPreferences } from "../types";
import { BrandIllustration, IconButton } from "./common";

type SectionId = "assistant" | "user" | "appearance" | "ai" | "memory" | "skills" | "status";

const sections: Array<{ id: SectionId; label: string; icon: typeof Bot; aliases: string }> = [
  { id: "assistant", label: "Bobodan", icon: Bot, aliases: "助手 人设 教学 回答 反馈 昵称" },
  { id: "user", label: "我与学习", icon: CircleUserRound, aliases: "用户 称呼 简介 目标 学习" },
  { id: "appearance", label: "界面与阅读", icon: BookOpenText, aliases: "外观 字体 字号 宽度 纸纹 动效 会话密度" },
  { id: "ai", label: "AI 与模型", icon: Cpu, aliases: "模型 provider 供应商 连接 deepseek minimax openai" },
  { id: "memory", label: "记忆与数据", icon: Brain, aliases: "记忆 隐私 本地 数据 资料库" },
  { id: "skills", label: "Skills", icon: Wrench, aliases: "技能 命令 能力 skill" },
  { id: "status", label: "状态与关于", icon: Activity, aliases: "状态 后端 索引 版本 连接" },
];

function SettingRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <div className="setting-row"><span><strong>{label}</strong>{hint && <small>{hint}</small>}</span><div>{children}</div></div>;
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return <button type="button" className={`setting-toggle ${checked ? "on" : ""}`} role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}><i /></button>;
}

function Segmented<T extends string | number>({ value, options, onChange, label }: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  label: string;
}) {
  return <div className="setting-segmented" role="radiogroup" aria-label={label}>{options.map((option) => <button type="button" role="radio" aria-checked={option.value === value} className={option.value === value ? "active" : ""} key={String(option.value)} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>;
}

export function SettingsDialog({
  settings,
  activeLibrary,
  section,
  onSectionChange,
  onClose,
  onSettingsChange,
}: {
  settings: SettingsSummary;
  activeLibrary: LibrarySummary | null;
  section: string;
  onSectionChange: (section: SectionId) => void;
  onClose: () => void;
  onSettingsChange: (settings: SettingsSummary) => void;
}) {
  const active = sections.some((item) => item.id === section) ? section as SectionId : "assistant";
  const [query, setQuery] = useState("");
  const [searchIndex, setSearchIndex] = useState(0);
  const [preferences, setPreferences] = useState(settings.preferences);
  const [profile, setProfile] = useState({ ...settings.preferences.user });
  const [assistant, setAssistant] = useState({ ...settings.preferences.assistant });
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [providerTest, setProviderTest] = useState<Record<string, string>>({});
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const activeNavRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    dialogRef.current?.focus();
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  useEffect(() => {
    setPreferences(settings.preferences);
    setProfile({ ...settings.preferences.user });
    setAssistant({ ...settings.preferences.assistant });
  }, [settings]);

  useEffect(() => {
    if (active !== "status" || runtimeStatus) return;
    void api.runtimeStatus().then(setRuntimeStatus).catch((reason: Error) => setError(reason.message));
  }, [active, runtimeStatus]);

  const matches = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return needle ? sections.filter((item) => `${item.label} ${item.aliases}`.toLocaleLowerCase().includes(needle)) : sections;
  }, [query]);

  useEffect(() => setSearchIndex(0), [query]);

  useEffect(() => {
    activeNavRef.current?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [active]);

  async function patchPreferences(patch: Record<string, unknown>) {
    if (saving) return;
    const previous = preferences;
    setSaving(true);
    setError("");
    try {
      const result = await api.patchPreferences(preferences.revision, patch);
      setPreferences(result.preferences);
      onSettingsChange({ ...settings, preferences: result.preferences, default_provider: result.preferences.ai.default_provider, skills: settings.skills.map((skill) => ({ ...skill, enabled: result.preferences.skills.enabled_names.includes(skill.name) })) });
      setNotice("设置已保存");
      window.setTimeout(() => setNotice(""), 1600);
    } catch (reason) {
      setPreferences(previous);
      setError(reason instanceof Error ? reason.message : "设置没有保存成功。");
    } finally {
      setSaving(false);
    }
  }

  async function saveAssistant() {
    await patchPreferences({ assistant });
  }

  async function saveProfile() {
    await patchPreferences({ user: profile });
  }

  async function testProvider(name: string) {
    setProviderTest((current) => ({ ...current, [name]: "正在测试…" }));
    try {
      const result = await api.providerTest(name);
      setProviderTest((current) => ({ ...current, [name]: `${result.latency_ms}ms · 连接正常` }));
    } catch (reason) {
      setProviderTest((current) => ({ ...current, [name]: reason instanceof Error ? reason.message : "连接失败" }));
    }
  }

  function sectionContent() {
    if (active === "assistant") return <>
      <div className="settings-identity"><BrandIllustration state="listening" size={92} alt="Bobodan" /><div><span>品牌角色</span><h3>Bobodan</h3><p>三花猫品牌保持固定，你可以调整它陪伴学习的方式。</p></div></div>
      <section className="settings-group"><header><h3>称呼与教学方式</h3><p>这些设置影响表达，不改变事实、来源和安全规则。</p></header>
        <label className="settings-field"><span>助手昵称</span><input maxLength={60} value={assistant.display_name} onChange={(event) => setAssistant({ ...assistant, display_name: event.target.value })} /></label>
        <SettingRow label="教学方式" hint="决定默认如何展开一次讲解"><Segmented label="教学方式" value={assistant.teaching_style} onChange={(value) => setAssistant({ ...assistant, teaching_style: value })} options={[{ value: "guided", label: "引导式" }, { value: "explanatory", label: "讲解式" }, { value: "practice", label: "陪练式" }]} /></SettingRow>
        <SettingRow label="回答深度"><Segmented label="回答深度" value={assistant.answer_depth} onChange={(value) => setAssistant({ ...assistant, answer_depth: value })} options={[{ value: "concise", label: "简洁" }, { value: "standard", label: "标准" }, { value: "deep", label: "深入" }]} /></SettingRow>
        <SettingRow label="反馈方式"><Segmented label="反馈方式" value={assistant.feedback_strength} onChange={(value) => setAssistant({ ...assistant, feedback_strength: value })} options={[{ value: "gentle", label: "温和" }, { value: "direct", label: "直接" }]} /></SettingRow>
        <footer><button className="primary-button" disabled={saving} onClick={() => void saveAssistant()}><Check size={15} />保存助手设置</button></footer>
      </section>
    </>;
    if (active === "user") return <section className="settings-group"><header><h3>你的学习资料</h3><p>用于调整讲解起点，不会作为公开资料或自动写入 Wiki。</p></header>
      <label className="settings-field"><span>怎么称呼你</span><input maxLength={60} value={profile.display_name} onChange={(event) => setProfile({ ...profile, display_name: event.target.value })} /></label>
      <label className="settings-field"><span>个人简介</span><textarea rows={5} maxLength={1000} value={profile.profile} onChange={(event) => setProfile({ ...profile, profile: event.target.value })} placeholder="例如：正在学习计算机基础，熟悉 Python。" /></label>
      <label className="settings-field"><span>长期学习目标</span><textarea rows={4} maxLength={500} value={profile.long_term_goal} onChange={(event) => setProfile({ ...profile, long_term_goal: event.target.value })} /></label>
      <footer><button className="primary-button" disabled={saving} onClick={() => void saveProfile()}><Check size={15} />保存我的资料</button></footer>
    </section>;
    if (active === "appearance") return <>
      <section className="settings-group"><header><h3>阅读排版</h3><p>高频操作仍使用系统黑体，正文阅读可以选择今楷或宋体。</p></header>
        <SettingRow label="阅读字体"><Segmented label="阅读字体" value={preferences.appearance.reading_font} onChange={(value) => void patchPreferences({ appearance: { reading_font: value } })} options={[{ value: "jin-kai", label: "今楷" }, { value: "noto-serif", label: "宋体" }]} /></SettingRow>
        <SettingRow label="正文字号"><Segmented label="正文字号" value={preferences.appearance.body_font_size} onChange={(value) => void patchPreferences({ appearance: { body_font_size: value } })} options={[15, 16, 17, 18].map((value) => ({ value: value as 15 | 16 | 17 | 18, label: `${value}` }))} /></SettingRow>
        <SettingRow label="内容宽度"><Segmented label="内容宽度" value={preferences.appearance.content_width} onChange={(value) => void patchPreferences({ appearance: { content_width: value } })} options={[{ value: 640, label: "窄" }, { value: 720, label: "标准" }, { value: 800, label: "宽" }]} /></SettingRow>
      </section>
      <section className="settings-group"><header><h3>界面感受</h3></header>
        <SettingRow label="纸张纹理" hint="保持轻微，不影响正文对比度"><Toggle label="纸张纹理" checked={preferences.appearance.paper_texture} onChange={(value) => void patchPreferences({ appearance: { paper_texture: value } })} /></SettingRow>
        <SettingRow label="会话列表密度"><Segmented label="会话列表密度" value={preferences.appearance.session_density} onChange={(value) => void patchPreferences({ appearance: { session_density: value } })} options={[{ value: "comfortable", label: "舒展" }, { value: "compact", label: "紧凑" }]} /></SettingRow>
        <SettingRow label="减少动态效果"><Toggle label="减少动态效果" checked={preferences.appearance.motion === "reduced"} onChange={(value) => void patchPreferences({ appearance: { motion: value ? "reduced" : "system" } })} /></SettingRow>
      </section>
    </>;
    if (active === "ai") return <section className="settings-group"><header><h3>模型与连接</h3><p>密钥继续由本地环境变量管理。测试连接会发送一次最小请求。</p></header>
      {settings.providers.map((provider) => <div className="provider-row" key={provider.name}><span className={`provider-mark ${provider.configured ? "ready" : ""}`}><Cpu size={17} /></span><div><strong>{provider.name}</strong><small>{provider.model || provider.type || "模型"}{providerTest[provider.name] ? ` · ${providerTest[provider.name]}` : ""}</small></div><label><input type="radio" name="default-provider" checked={preferences.ai.default_provider === provider.name} disabled={!provider.configured} onChange={() => void patchPreferences({ ai: { default_provider: provider.name } })} />默认</label><button className="quiet-button" disabled={!provider.configured} onClick={() => void testProvider(provider.name)}>测试连接</button></div>)}
    </section>;
    if (active === "memory") return <>
      <section className="settings-group"><header><h3>学习记忆</h3><p>关闭后新对话不会读取或写入学习记忆，已有内容不会自动删除。</p></header><SettingRow label="启用学习记忆"><Toggle label="启用学习记忆" checked={preferences.memory.enabled} onChange={(value) => void patchPreferences({ memory: { enabled: value } })} /></SettingRow></section>
      <section className="settings-boundary"><ShieldCheck size={20} /><div><strong>本地数据边界</strong><p>原始资料只读，设置不会把资料上传到 Bobodan 服务。当前资料库：{activeLibrary?.name || "尚未选择"}。</p></div></section>
    </>;
    if (active === "skills") return <section className="settings-group"><header><h3>Web 安全 Skills</h3><p>这里只显示浏览器运行时能够完整执行的学习技能。</p></header>{settings.skills.length ? settings.skills.map((skill) => <SettingRow key={skill.name} label={skill.name} hint={`${skill.description} · 来源：${skill.source}`}><span className="skill-setting-control"><small>{skill.capabilities.join(" · ")}</small><Toggle label={`${skill.name} 技能`} checked={preferences.skills.enabled_names.includes(skill.name)} onChange={(value) => { const names = value ? [...preferences.skills.enabled_names, skill.name] : preferences.skills.enabled_names.filter((item) => item !== skill.name); void patchPreferences({ skills: { enabled_names: names } }); }} /></span></SettingRow>) : <p className="settings-empty">当前没有可用于 Web 的 Skills。</p>}</section>;
    return <section className="settings-group"><header><h3>运行状态</h3><p>只展示普通用户能理解并采取行动的状态。</p></header>{runtimeStatus ? <div className="runtime-grid"><div><Activity /><span><strong>后端</strong><small>连接正常</small></span></div><div><Cpu /><span><strong>AI</strong><small>{runtimeStatus.providers.configured}/{runtimeStatus.providers.available} 已配置</small></span></div><div><Database /><span><strong>资料索引</strong><small>{runtimeStatus.knowledge.state === "ready" ? `${runtimeStatus.knowledge.documents} 份资料` : "等待资料"}</small></span></div><div><Brain /><span><strong>记忆</strong><small>{runtimeStatus.memory.enabled ? "已启用" : "已关闭"}</small></span></div><div><Wrench /><span><strong>Skills</strong><small>{runtimeStatus.skills.enabled}/{runtimeStatus.skills.available} 已启用</small></span></div><div><Gauge /><span><strong>版本</strong><small>{runtimeStatus.version}</small></span></div></div> : <p className="settings-empty">正在读取状态…</p>}</section>;
  }

  return <div className="settings-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="settings-dialog" role="dialog" aria-modal="true" aria-label="设置" tabIndex={-1} ref={dialogRef}>
    <header className="settings-dialog-header"><button className="settings-back" onClick={onClose} aria-label="返回"><ChevronLeft /></button><strong>设置</strong><h2>{sections.find((item) => item.id === active)?.label}</h2><IconButton label="关闭设置" onClick={onClose}><X /></IconButton></header>
    <div className="settings-dialog-body"><nav className="settings-nav" aria-label="设置分类"><label className="settings-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (!matches.length) return; if (event.key === "ArrowDown") { event.preventDefault(); setSearchIndex((current) => (current + 1) % matches.length); } else if (event.key === "ArrowUp") { event.preventDefault(); setSearchIndex((current) => (current - 1 + matches.length) % matches.length); } else if (event.key === "Enter") { event.preventDefault(); onSectionChange(matches[Math.min(searchIndex, matches.length - 1)].id); } }} placeholder="搜索设置" />{query && <button onClick={() => setQuery("")} aria-label="清空搜索"><X size={13} /></button>}</label>{matches.map(({ id, label, icon: Icon }, index) => <button ref={active === id ? activeNavRef : undefined} className={`${active === id ? "active" : ""} ${query && searchIndex === index ? "search-active" : ""}`} key={id} onClick={() => onSectionChange(id)}><Icon size={17} /><span>{label}</span></button>)}</nav><main className="settings-main">{error && <div className="settings-error">{error}</div>}{notice && <div className="settings-notice"><Check size={14} />{notice}</div>}<div className="settings-page-heading"><Sparkles size={16} /><span>Bobodan Settings</span><h2>{sections.find((item) => item.id === active)?.label}</h2></div>{sectionContent()}</main></div>
  </section></div>;
}

export function SettingsUnavailableDialog({
  reconnecting,
  onRetry,
  onClose,
}: {
  reconnecting: boolean;
  onRetry: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  return <div className="settings-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings-dialog settings-unavailable" role="dialog" aria-modal="true" aria-label="设置" tabIndex={-1}>
      <header className="settings-dialog-header"><button className="settings-back" onClick={onClose} aria-label="返回"><ChevronLeft /></button><strong>设置</strong><h2>连接状态</h2><IconButton label="关闭设置" onClick={onClose}><X /></IconButton></header>
      <main className="settings-unavailable-main">
        <span className="settings-unavailable-icon"><Activity size={24} /></span>
        <div><span>Bobodan Settings</span><h2>设置暂时不可用</h2><p>学习页面仍可查看，但需要重新连接本地后端才能读取或修改设置。</p></div>
        <button className="primary-button" disabled={reconnecting} onClick={onRetry}>{reconnecting ? <><RefreshCw className="spin" size={15} />正在重连</> : <><RefreshCw size={15} />重新连接</>}</button>
      </main>
    </section>
  </div>;
}
