import { BookOpen, ExternalLink, Globe2 } from "lucide-react";

import type { WebCandidatesArtifact } from "../../types";

const qualityLabels = { official: "官方/教育", reference: "参考资料", community: "社区内容", unknown: "普通网页" };

export function WebCandidatesCard({ artifact, selected, busy, onToggle, onUse }: {
  artifact: WebCandidatesArtifact;
  selected: string[];
  busy: boolean;
  onToggle: (artifact: WebCandidatesArtifact, candidateId: string) => void;
  onUse: (artifact: WebCandidatesArtifact) => void;
}) {
  const selectable = artifact.status === "ready" || artifact.status === "partial" || (artifact.status === "failed" && artifact.candidates.length > 0);
  return <section className={`web-candidates-card ${artifact.status}`}>
    <header><span><Globe2 size={15} />网页候选</span><strong>{artifact.status === "failed" ? "没有找到可用来源" : artifact.status === "fetching" ? "正在读取来源" : artifact.status === "used" ? "已选择来源" : `找到 ${artifact.candidates.length} 个候选`}</strong></header>
    <p>搜索摘要只用于选择，勾选后才会读取网页正文。最多选择 4 个。</p>
    {artifact.candidates.length > 0 && <div className="web-candidate-list">{artifact.candidates.map((candidate) => <label className={selected.includes(candidate.candidate_id) ? "selected" : ""} key={candidate.candidate_id}><input type="checkbox" checked={selected.includes(candidate.candidate_id)} disabled={!selectable || busy} onChange={() => onToggle(artifact, candidate.candidate_id)} /><span><strong>{candidate.title}</strong><small>{candidate.domain} · {qualityLabels[candidate.quality_hint]}</small><p>{candidate.snippet}</p></span><a href={candidate.url} target="_blank" rel="noreferrer" aria-label={`打开 ${candidate.title}`} onClick={(event) => event.stopPropagation()}><ExternalLink size={14} /></a></label>)}</div>}
    {selectable && <footer><small>{selected.length ? `已选择 ${selected.length} 个来源` : artifact.status === "ready" ? "尚未选择来源" : "可以重新选择来源并重试"}</small><button className="primary-button" disabled={!selected.length || busy} onClick={() => onUse(artifact)}><BookOpen size={15} />{artifact.status === "ready" ? "使用选中来源" : "重新读取来源"}</button></footer>}
  </section>;
}
