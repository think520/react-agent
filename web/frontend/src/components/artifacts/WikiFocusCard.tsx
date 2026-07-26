import type { WikiFocusArtifact } from "../../types";

export function WikiFocusCard({ artifact, busy, onAdjust, onConfirm }: {
  artifact: WikiFocusArtifact;
  busy: boolean;
  onAdjust: () => void;
  onConfirm: (artifact: WikiFocusArtifact) => void;
}) {
  return <section className="wiki-focus-card">
    <header><span>Wiki Focus</span><strong>先确认整理重点</strong></header>
    <p>资料范围：{artifact.scope.documents.join("、")}</p>
    {artifact.instruction && <blockquote>{artifact.instruction}</blockquote>}
    {artifact.status === "awaiting_confirmation" && <footer>
      <button className="quiet-button" onClick={onAdjust}>调整重点</button>
      <button className="primary-button" disabled={busy} onClick={() => onConfirm(artifact)}>按此重点继续</button>
    </footer>}
    {artifact.status === "confirmed" && <small>重点已确认，计划已生成。</small>}
  </section>;
}
