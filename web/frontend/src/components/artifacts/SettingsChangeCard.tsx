import { Check } from "lucide-react";

import type { SettingsChangeArtifact } from "../../types";

function displaySettingValue(value: unknown) {
  if (value === true) return "开启";
  if (value === false) return "关闭";
  const labels: Record<string, string> = {
    concise: "简洁", standard: "标准", deep: "深入",
    guided: "引导式", explanatory: "讲解式", practice: "陪练式",
    gentle: "温和", direct: "直接",
  };
  return labels[String(value)] || String(value);
}

export function SettingsChangeCard({ artifact, busy, onResolve }: {
  artifact: SettingsChangeArtifact;
  busy: boolean;
  onResolve: (artifact: SettingsChangeArtifact, action: "apply" | "reject") => void;
}) {
  return <section className={`settings-change-card ${artifact.status}`}>
    <header><span>设置变更</span><strong>{artifact.status === "pending" ? "确认后才会生效" : artifact.status === "applied" ? "设置已更新" : "已取消修改"}</strong></header>
    <div className="settings-change-list">{artifact.changes.map((change) => <div key={change.key}><span>{change.label}</span><del>{displaySettingValue(change.before)}</del><i>→</i><strong>{displaySettingValue(change.after)}</strong></div>)}</div>
    {artifact.status === "pending" && <footer><button className="quiet-button" disabled={busy} onClick={() => onResolve(artifact, "reject")}>取消</button><button className="primary-button" disabled={busy} onClick={() => onResolve(artifact, "apply")}><Check size={15} />确认修改</button></footer>}
  </section>;
}
