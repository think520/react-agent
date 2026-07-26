import { Globe2 } from "lucide-react";

import type { WebConsentArtifact } from "../../types";

export function WebConsentCard({ artifact, busy, onResolve }: {
  artifact: WebConsentArtifact;
  busy: boolean;
  onResolve: (artifact: WebConsentArtifact, action: "approve" | "reject") => void;
}) {
  return <section className={`web-consent-card ${artifact.status}`}>
    <header><span><Globe2 size={15} />联网资料</span><strong>{artifact.status === "pending" ? "本地证据暂时不足" : artifact.status === "approved" ? "已同意联网查找" : "已继续使用本地资料"}</strong></header>
    <p>{artifact.reason}</p><blockquote>{artifact.query}</blockquote>
    {artifact.status === "pending" && <footer><button className="quiet-button" disabled={busy} onClick={() => onResolve(artifact, "reject")}>只用本地资料</button><button className="primary-button" disabled={busy} onClick={() => onResolve(artifact, "approve")}><Globe2 size={15} />联网查找</button></footer>}
  </section>;
}
