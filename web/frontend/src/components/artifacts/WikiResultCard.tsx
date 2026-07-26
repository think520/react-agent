import type { WikiResultArtifact } from "../../types";

export function WikiResultCard({ artifact, busy, onUndo }: {
  artifact: WikiResultArtifact;
  busy: boolean;
  onUndo: (artifact: WikiResultArtifact) => void;
}) {
  return <section className={`wiki-result-card ${artifact.status}`}>
    <header><span>Wiki Result</span><strong>{artifact.status === "restored" ? "已恢复检查点" : "Wiki 已写入"}</strong></header>
    {artifact.kept_existing?.length ? <p>已保留“{artifact.kept_existing.join("、")}”的原页面，并写入其余 {artifact.written?.length || 0} 个页面。</p> : artifact.written?.length ? <p>本轮写入 {artifact.written.length} 个页面。</p> : <p>{artifact.status === "restored" ? "本轮变更已经撤销。" : "已保存变更和检查点。"}</p>}
    {artifact.status === "applied" && artifact.checkpoint_id && <footer><button className="quiet-button" disabled={busy} onClick={() => onUndo(artifact)}>撤销本轮写入</button></footer>}
  </section>;
}
