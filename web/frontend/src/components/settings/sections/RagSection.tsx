import { useEffect, useState } from "react";
import { Activity, Database, Search } from "lucide-react";

import { api } from "../../../lib/api";
import type { RuntimeStatus } from "../../../types";
import { SettingsSection } from "../SettingsPrimitives";

/** 设置 · 检索与 RAG（2026-10-17 S4）：只读状态与术语说明，写路径仍走后端配置。 */
export function RagSection() {
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  useEffect(() => { void api.runtimeStatus().then(setRuntime).catch(() => setRuntime(null)); }, []);
  return <>
    <SettingsSection title="检索状态" description="资料库检索走「向量 + FTS5 → RRF」，无向量能力时降级为纯文本检索，并在回答里明确提示。">
      <div className="runtime-grid">
        <div><Activity /><span><strong>后端</strong><small>{runtime ? "连接正常" : "正在读取…"}</small></span></div>
        <div><Database /><span><strong>资料索引</strong><small>{runtime ? (runtime.knowledge.state === "ready" ? runtime.knowledge.documents + " 份资料" : "等待资料") : "—"}</small></span></div>
        <div><Search /><span><strong>检索模式</strong><small>hybrid · 向量可用时自动融合；不可用时 fts_only</small></span></div>
      </div>
    </SettingsSection>

    <SettingsSection title="术语词汇表" description="请求词表与上报词表不是一回事：请求用 auto / hybrid / directory / directory_grep，回答里上报 fts_only / hybrid / unavailable。">
      <dl className="rag-glossary">
        <div><dt>hybrid</dt><dd>向量召回 + 全文检索 → RRF 融合；最常用。</dd></div>
        <div><dt>fts_only</dt><dd>向量不可用时的降级：只走 SQLite FTS5（中文 2-gram）。</dd></div>
        <div><dt>unavailable</dt><dd>索引不存在或未同步，检索不可用。</dd></div>
        <div><dt>directory / directory_grep</dt><dd>按资料目录路由到具体文档，再在原文里定位段落。</dd></div>
      </dl>
    </SettingsSection>

    <SettingsSection title="评测与降级可见性" description="检索质量由真实资料库的评测集守护；降级提示会显示在回答与检索面板里。">
      <p className="settings-model-hint">评测集在 <code>docs/RAG_EVAL.md</code> 里维护（29 条真实用例），变动检索权重前先跑一次基线；前端在 <code>RetrievalDegradedNotice</code> 中呈现降级原因与命中数。</p>
    </SettingsSection>
  </>;
}
