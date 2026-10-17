import { Check } from "lucide-react";

import { BrandIllustration } from "../../common";
import type { UserPreferences } from "../../../types";
import { SettingsField, SettingsRow, SettingsSection, SettingsSegmented } from "../SettingsPrimitives";

type AssistantPrefs = UserPreferences["assistant"];

/** 设置 · Bobodan（2026-10-17 S2：搬进设计系统原语，行为不变）。 */
export function AssistantSection({ assistant, setAssistant, saving, onSave }: {
  assistant: AssistantPrefs;
  setAssistant: (next: AssistantPrefs) => void;
  saving: boolean;
  onSave: () => Promise<void> | void;
}) {
  return <>
    <div className="settings-identity">
      <BrandIllustration state="listening" size={92} alt="Bobodan" />
      <div><span>品牌角色</span><h3>Bobodan</h3><p>三花猫品牌保持固定，你可以调整它陪伴学习的方式。</p></div>
    </div>
    <SettingsSection
      title="称呼与教学方式"
      description="这些设置影响表达，不改变事实、来源和安全规则。"
      footer={<button className="primary-button" disabled={saving} onClick={() => void onSave()}><Check size={15} />保存助手设置</button>}
    >
      <SettingsField label="助手昵称">
        <input maxLength={60} value={assistant.display_name} onChange={(event) => setAssistant({ ...assistant, display_name: event.target.value })} />
      </SettingsField>
      <SettingsRow label="教学方式" hint="决定默认如何展开一次讲解">
        <SettingsSegmented label="教学方式" value={assistant.teaching_style} onChange={(value) => setAssistant({ ...assistant, teaching_style: value })} options={[{ value: "guided", label: "引导式" }, { value: "explanatory", label: "讲解式" }, { value: "practice", label: "陪练式" }]} />
      </SettingsRow>
      <SettingsRow label="回答深度">
        <SettingsSegmented label="回答深度" value={assistant.answer_depth} onChange={(value) => setAssistant({ ...assistant, answer_depth: value })} options={[{ value: "concise", label: "简洁" }, { value: "standard", label: "标准" }, { value: "deep", label: "深入" }]} />
      </SettingsRow>
      <SettingsRow label="反馈方式">
        <SettingsSegmented label="反馈方式" value={assistant.feedback_strength} onChange={(value) => setAssistant({ ...assistant, feedback_strength: value })} options={[{ value: "gentle", label: "温和" }, { value: "direct", label: "直接" }]} />
      </SettingsRow>
    </SettingsSection>
  </>;
}
