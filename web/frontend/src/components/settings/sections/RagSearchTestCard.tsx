import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";

import { api } from "../../../lib/api";
import { formatEffectiveModeLabel, formatRetrieverChannel } from "../../../lib/retrievalStatus";
import type { RagSearchTestResponse } from "../../../types";
import { SettingsSection } from "../SettingsPrimitives";

/** 交互式召回测试沙盒：空库自动收拢，有资料时支持真实主题一键试搜与命中链路诊断。 */
export function RagSearchTestCard({
  knowledgeReady,
  sampleQueries = [],
}: {
  knowledgeReady: boolean;
  sampleQueries?: string[];
}) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RagSearchTestResponse | null>(null);

  useEffect(() => {
    if (!knowledgeReady) {
      setResult(null);
      setError("");
    }
  }, [knowledgeReady]);

  async function runQuery(rawQuery: string) {
    const cleaned = rawQuery.trim();
    if (!cleaned || busy || !knowledgeReady) return;
    setBusy(true);
    setError("");
    try {
      const response = await api.testRagSearch(cleaned, 5, "auto");
      setResult(response);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "召回测试失败");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    void runQuery(query);
  }

  function handleChipClick(sample: string) {
    setQuery(sample);
    void runQuery(sample);
  }

  function handleClear() {
    setResult(null);
    setError("");
  }

  if (!knowledgeReady) {
    return (
      <SettingsSection
        title="召回测试"
        description="用资料库里的真实问题试搜，验证混合检索与原文命中片段。"
      >
        <p className="settings-empty">
          当前资料库还没有文档；前往「资料库」导入并同步资料后，即可在这里试搜验证。
        </p>
      </SettingsSection>
    );
  }

  return (
    <SettingsSection
      title="召回测试"
      description="用资料库里的真实问题试搜，立刻看到实际走的是「混合检索」还是「仅关键词」，以及每条命中的来源。"
    >
      {sampleQueries.length > 0 && (
        <div className="rag-chip-row">
          <span>试试真实资料主题：</span>
          {sampleQueries.map((sample) => (
            <button
              key={sample}
              type="button"
              className="rag-chip"
              data-active={query.trim() === sample}
              disabled={busy}
              onClick={() => handleChipClick(sample)}
            >
              {sample}
            </button>
          ))}
        </div>
      )}

      <form className="rag-test-bar" onSubmit={onSubmit}>
        <input
          value={query}
          disabled={busy}
          maxLength={200}
          placeholder="输入一个问题或关键词试试召回效果…"
          aria-label="召回测试关键词"
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="quiet-button" type="submit" disabled={busy || !query.trim()}>
          <Search size={14} />
          {busy ? "检索中…" : "测试召回"}
        </button>
        {(result || error) && (
          <button className="quiet-button" type="button" disabled={busy} onClick={handleClear}>
            <X size={14} />
            清空
          </button>
        )}
      </form>

      {error && <div className="settings-error">{error}</div>}

      {result && (
        <div className="rag-test-result">
          <div className="rag-test-summary">
            <span className="rag-mode-badge" data-tone={result.retrieval_mode === "hybrid" ? "ready" : "muted"}>
              实际模式：{formatEffectiveModeLabel(result.retrieval_mode)}
            </span>
            <small>耗时 {result.latency_ms}ms · 命中 {result.results.length} 条</small>
          </div>
          {result.semantic_reason && !result.semantic_available && (
            <p className="settings-model-hint">
              降级说明：{result.semantic_reason.detail}
            </p>
          )}
          {result.results.length > 0 ? (
            <div className="rag-hit-list">
              {result.results.map((hit, index) => {
                const channel = formatRetrieverChannel(hit.retrievers);
                return (
                  <article className="rag-hit-card" key={`${hit.chunk_id || hit.source}-${index}`}>
                    <header className="rag-hit-head">
                      <span
                        className="rag-hit-rank"
                        title={`原始融合分 ${hit.score.toFixed(4)}`}
                      >
                        #{index + 1}
                      </span>
                      <strong>{hit.title || hit.source}</strong>
                      <span className="rag-hit-channel" data-hybrid={channel.isHybrid}>
                        {channel.label}
                      </span>
                    </header>
                    {(hit.heading_text || hit.source) && (
                      <small className="rag-hit-meta">
                        {hit.source}
                        {hit.heading_text ? ` · ${hit.heading_text}` : ""}
                      </small>
                    )}
                    <p className="rag-hit-snippet">{hit.snippet || "（无文本预览）"}</p>
                  </article>
                );
              })}
            </div>
          ) : (
            <p className="settings-empty">没有命中相关片段，可以换个关键词再试，或先同步资料。</p>
          )}
        </div>
      )}
    </SettingsSection>
  );
}
