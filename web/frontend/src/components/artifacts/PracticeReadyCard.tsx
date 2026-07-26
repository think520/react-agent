import { BookOpen } from "lucide-react";

import type { PracticeReadyArtifact } from "../../types";
import { AttributionBadges, BrandIllustration } from "../common";

export function PracticeReadyCard({ artifact, starting, onStart }: {
  artifact: PracticeReadyArtifact;
  starting: boolean;
  onStart: (artifact: PracticeReadyArtifact) => void;
}) {
  return <section className={`practice-ready-card ${artifact.status}`}>
    <BrandIllustration state="ready" size={56} />
    <div><header><span>练习已就绪</span><strong>{artifact.count} 道题已经准备好</strong></header><p>{artifact.topic}</p><AttributionBadges attribution={artifact.attribution} /></div>
    <button className="primary-button" disabled={starting} onClick={() => onStart(artifact)}><BookOpen size={15} />{artifact.status === "started" ? "继续练习" : starting ? "正在打开" : "开始练习"}</button>
  </section>;
}
