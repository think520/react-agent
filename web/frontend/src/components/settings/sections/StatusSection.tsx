import { Activity, Brain, Cpu, Database, Gauge, Search, Wrench } from "lucide-react";

import type { RuntimeStatus } from "../../../types";
import { SettingsSection } from "../SettingsPrimitives";

/** 设置 · 状态与关于（2026-10-17 S2；内容与迁移前一致）。 */
export function StatusSection({ runtimeStatus }: { runtimeStatus: RuntimeStatus | null }) {
  return <SettingsSection title="运行状态" description="只展示普通用户能理解并采取行动的状态。">
    {runtimeStatus ? <div className="runtime-grid">
      <div><Activity /><span><strong>后端</strong><small>连接正常</small></span></div>
      <div><Cpu /><span><strong>AI</strong><small>{runtimeStatus.providers.configured}/{runtimeStatus.providers.available} 已配置</small></span></div>
      <div><Search /><span><strong>联网搜索</strong><small>{runtimeStatus.search.permission === "auto" ? "模型自动" : "每次询问"} · {runtimeStatus.search.default} · {runtimeStatus.search.jina_fallback ? "Jina 后备开启" : "仅直接读取"}</small></span></div>
      <div><Database /><span><strong>资料索引</strong><small>{runtimeStatus.knowledge.state === "ready" ? `${runtimeStatus.knowledge.documents} 份资料` : "等待资料"}</small></span></div>
      <div><Brain /><span><strong>记忆</strong><small>{runtimeStatus.memory.enabled ? "已启用" : "已关闭"}</small></span></div>
      <div><Wrench /><span><strong>Skills</strong><small>{runtimeStatus.skills.enabled}/{runtimeStatus.skills.available} 已启用</small></span></div>
      <div><Gauge /><span><strong>版本</strong><small>{runtimeStatus.version}</small></span></div>
    </div> : <p className="settings-empty">正在读取状态…</p>}
  </SettingsSection>;
}
