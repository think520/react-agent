import { BookOpen, ExternalLink } from "lucide-react";

import type { WebEvidenceArtifact } from "../../types";

export function WebEvidenceCard({ artifact }: { artifact: WebEvidenceArtifact }) {
  return <section className={`web-evidence-card ${artifact.status}`}>
    <header><span><BookOpen size={15} />网页证据</span><strong>{artifact.status === "failed" ? "来源读取失败" : artifact.status === "partial" ? "部分来源可用" : "证据快照已保存"}</strong></header>
    {artifact.sources.length ? <div>{artifact.sources.map((source) => <a href={source.url || "#"} target="_blank" rel="noreferrer" key={source.source_id}><span><strong>{source.title}</strong><small>{source.domain} · {source.reader === "jina" ? "Jina Reader 后备" : "直接读取"} · {source.accessed_at ? new Date(source.accessed_at).toLocaleString("zh-CN") : ""}</small></span><ExternalLink size={14} /></a>)}</div> : <p>这些网页没有返回可核实的正文，未用于回答。</p>}
  </section>;
}
