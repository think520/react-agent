import { useState } from "react";
import { Search } from "lucide-react";

import { api } from "../../../lib/api";
import type { RagSearchTestResponse } from "../../../types";
import { SettingsSection } from "../SettingsPrimitives";

function retrieverBadges(retrievers: string[]): string {
  const hasVec = retrievers.includes("vector");
  const hasFts = retrievers.some((item) => item === "fts5" || item === "fts" || item === "keyword");
  if (hasVec && hasFts) return "向量 + 全文双路命中";
  if (hasVec) return "语义向量命中";
  if (hasFts || retrievers.length === 0) return "全文关键词命中";
  return retrievers.join(" + ");
}

/** 交互式召回测试沙盒（Dify / RAGFlow 共性能力）：验证当前资料库实际走的检索链路与命中片段。 */
export function RagSearchTestCard({ knowledgeReady }: { knowledgeReady: boolean }) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RagSearchTestResponse | null>(null);

  async function runTest(event?: React.FormEvent) {
    event?.preventDefault();
    const cleaned = query.trim();
    if (!cleaned || busy) return;
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

  return (
    <SettingsSection
      title="召回测试"
      description="用你资料库里的真实问题试搜一下，立刻看到实际走的是「混合检索」还是「纯文本」，以及每条命中的来源与通路。"
    >
      <form className="rag-test-bar" onSubmit={(event) => void runTest(event)}>
        <input
          value={query}
          disabled={busy || !knowledgeReady}
          maxLength={200}
          placeholder={knowledgeReady ? "输入一个问题或关键词试试召回效果…" : "请先导入并同步资料后再试搜"}
          aria-label="召回测试关键词"
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="quiet-button" type="submit" disabled={busy || !knowledgeReady || !query.trim()}>
          <Search size={14} />
          {busy ? "检索中…" : "测试召回"}
        </button>
      </form>

      {error && <div className="settings-error">{error}</div>}

      {result && (
        <div className="rag-test-result">
          <div className="rag-test-summary">
            <span className="rag-mode-badge" data-tone={result.retrieval_mode === "hybrid" ? "ready" : "muted"}>
              实际模式：{result.retrieval_mode === "hybrid" ? "hybrid（向量 + 全文融合）" : result.retrieval_mode}
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
              {result.results.map((hit, index) => (
                <article className="rag-hit-card" key={`${hit.chunk_id || hit.source}-${index}`}>
                  <header className="rag-hit-head">
                    <strong>{hit.title || hit.source}</strong>
                    <span className="rag-hit-channel">{retrieverBadges(hit.retrievers)}</span>
                    <small>得分 {hit.score.toFixed(3)}</small>
                  </header>
                  {(hit.heading_text || hit.source) && (
                    <small className="rag-hit-meta">
                      {hit.source}
                      {hit.heading_text ? ` · ${hit.heading_text}` : ""}
                    </small>
                  )}
                  <p className="rag-hit-snippet">{hit.snippet || "（无文本预览）"}</p>
                </article>
              ))}
            </div>
          ) : (
            <p className="settings-empty">没有命中相关片段，可以换个关键词再试，或先同步资料。</p>
          )}
        </div>
      )}
    </SettingsSection>
  );
}
