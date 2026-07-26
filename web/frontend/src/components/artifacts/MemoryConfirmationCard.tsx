import { Brain, Check } from "lucide-react";

import type { MemoryConfirmationArtifact } from "../../types";

export function MemoryConfirmationCard({ artifact, busy, onResolve }: {
  artifact: MemoryConfirmationArtifact;
  busy: boolean;
  onResolve: (artifact: MemoryConfirmationArtifact, action: "confirm" | "reject") => void;
}) {
  return <section className={`memory-confirmation-card ${artifact.status}`}>
    <header><span><Brain size={15} />个人知识</span><strong>{artifact.status === "pending" ? "确认后才会长期记住" : artifact.status === "confirmed" ? "已经记住" : "没有保存"}</strong></header>
    <div className="memory-confirmation-content"><small>{artifact.scope === "global" ? "所有资料库" : "当前资料库"} · {artifact.kind}</small><h4>{artifact.title}</h4>{artifact.before && <del>{artifact.before.content}</del>}<p>{artifact.content}</p></div>
    {artifact.requires_warning && artifact.status === "pending" && <div className="memory-sensitive-warning">这可能涉及健康、身份或其他敏感信息。确认后只保存在本地，你可以随时编辑或删除。</div>}
    {artifact.status === "pending" && <footer><button className="quiet-button" disabled={busy} onClick={() => onResolve(artifact, "reject")}>不保存</button><button className="primary-button" disabled={busy} onClick={() => onResolve(artifact, "confirm")}><Check size={15} />{artifact.requires_warning ? "了解并记住" : "确认记住"}</button></footer>}
  </section>;
}
