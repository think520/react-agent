import { useState } from "react";
import { Brain, Database, ShieldCheck } from "lucide-react";

import type { LegacyGraphPreview, LibrarySummary, MemoryOverview, UserPreferences } from "../../../types";
import { SettingsRow, SettingsSection, SettingsToggle } from "../SettingsPrimitives";
import { MemoryManagerPanel } from "../memory/MemoryManagerPanel";

/**
 * 设置 · 记忆与数据（2026-10-17 S4）。
 * 管理个人知识从嵌套弹窗改为**节内展开面板**；旧数据迁移与边界说明保持原逻辑。
 */
export function MemorySection({ preferences, patch, memoryOverview, activeLibrary, legacyGraph, legacyConceptIds, setLegacyConceptIds, legacyMemoryIds, setLegacyMemoryIds, recommendedMemories, allConceptsSelected, allRecommendedMemoriesSelected, migrationBusy, setConfirmLegacy }: {
  preferences: UserPreferences;
  patch: (patch: Record<string, unknown>) => void;
  memoryOverview: MemoryOverview | null;
  activeLibrary: LibrarySummary | null;
  legacyGraph: LegacyGraphPreview | null;
  legacyConceptIds: string[];
  setLegacyConceptIds: (next: string[]) => void;
  legacyMemoryIds: string[];
  setLegacyMemoryIds: (next: string[]) => void;
  recommendedMemories: LegacyGraphPreview["memories"];
  allConceptsSelected: boolean;
  allRecommendedMemoriesSelected: boolean;
  migrationBusy: boolean;
  setConfirmLegacy: (next: "migrate" | "archive" | null) => void;
}) {
  const [managerOpen, setManagerOpen] = useState(false);
  return <>
    <SettingsSection title="学习记忆" description="关闭后停止候选整理、长期知识写入和个性化；做题进度、错题和掌握度仍会保存。">
      <SettingsRow label="启用学习记忆">
        <SettingsToggle label="启用学习记忆" checked={preferences.memory.enabled} onChange={(value) => patch({ memory: { enabled: value } })} />
      </SettingsRow>
      <SettingsRow label="个人知识" hint={(memoryOverview?.knowledge_count || 0) + " 条已确认 · " + (memoryOverview?.pending_candidate_count || 0) + " 条待确认"}>
        <button className="quiet-button" type="button" disabled={!activeLibrary} onClick={() => setManagerOpen((current) => !current)}><Brain size={15} />{managerOpen ? "收起管理" : "管理个人知识"}</button>
      </SettingsRow>
      {managerOpen && <MemoryManagerPanel memoryEnabled={preferences.memory.enabled} onClose={() => setManagerOpen(false)} />}
    </SettingsSection>

    {legacyGraph?.detected && <SettingsSection title="旧版知识图谱迁移" description="旧 JSON 不再参与回答。逐项核对后导入候选区，校验成功才归档原文件。">
      <SettingsRow label="概念候选" hint={legacyConceptIds.length + "/" + legacyGraph.concepts.length + " 个已选择 · " + legacyGraph.relationships + " 条语义关系"}>
        <label className="migration-check"><input type="checkbox" checked={allConceptsSelected} onChange={(event) => setLegacyConceptIds(event.target.checked ? legacyGraph.concepts.map((item) => item.id) : [])} />选择全部</label>
      </SettingsRow>
      {legacyGraph.concepts.length > 0 && <details className="migration-preview"><summary>查看概念列表</summary><div>{legacyGraph.concepts.map((item) => <label key={item.id}><input type="checkbox" checked={legacyConceptIds.includes(item.id)} onChange={(event) => setLegacyConceptIds(event.target.checked ? [...legacyConceptIds, item.id] : legacyConceptIds.filter((id) => id !== item.id))} /><span><strong>{item.name}</strong><small>进入知识地图候选区，仍需审查</small></span></label>)}</div></details>}
      <SettingsRow label="旧记忆候选" hint={legacyMemoryIds.length + "/" + recommendedMemories.length + " 条已选择 · " + legacyGraph.memories.filter((item) => item.quality === "name_only").length + " 条只有名称"}>
        <label className="migration-check"><input type="checkbox" checked={allRecommendedMemoriesSelected} onChange={(event) => setLegacyMemoryIds(event.target.checked ? recommendedMemories.map((item) => item.id) : [])} />选择建议项</label>
      </SettingsRow>
      {legacyGraph.memories.length > 0 && <details className="migration-preview"><summary>查看记忆风险</summary><div>{legacyGraph.memories.map((item) => <label className={!item.recommended ? "disabled" : ""} key={item.id}><input type="checkbox" disabled={!item.recommended} checked={legacyMemoryIds.includes(item.id)} onChange={(event) => setLegacyMemoryIds(event.target.checked ? [...legacyMemoryIds, item.id] : legacyMemoryIds.filter((id) => id !== item.id))} /><span><strong>{item.name}</strong><small>{item.covered_by_legacy_memory ? "已由旧记忆迁移流程覆盖" : item.possible_duplicate ? "可能与「" + item.possible_duplicate + "」重复，请自行判断" : item.quality === "name_only" ? "只有名称，导入后参考价值可能较低" : "内容较完整"}</small></span></label>)}</div></details>}
      {Object.keys(legacyGraph.excluded).length > 0 && <p className="settings-warning">不会进入概念图谱：{Object.entries(legacyGraph.excluded).map(([label, count]) => label + " " + count + " 个").join(" · ")}</p>}
      <div className="migration-actions"><button className="danger-text-button" type="button" disabled={migrationBusy} onClick={() => setConfirmLegacy("archive")}>全部跳过并归档</button><button className="quiet-button" type="button" disabled={migrationBusy || (!legacyConceptIds.length && !legacyMemoryIds.length)} onClick={() => setConfirmLegacy("migrate")}><Database size={15} />{migrationBusy ? "正在处理…" : "迁移所选数据"}</button></div>
    </SettingsSection>}

    <section className="settings-boundary"><ShieldCheck size={20} /><div><strong>本地数据边界</strong><p>原始资料只读，设置不会把资料上传到 Bobodan 服务。当前资料库：{activeLibrary?.name || "尚未选择"}。</p></div></section>
  </>;
}
