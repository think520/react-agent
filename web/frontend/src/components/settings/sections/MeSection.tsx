import { Check } from "lucide-react";

import type { UserPreferences } from "../../../types";
import { SettingsField, SettingsSection } from "../SettingsPrimitives";

type Profile = UserPreferences["user"];

/** 设置 · 我与学习（2026-10-17 S2）。 */
export function MeSection({ profile, setProfile, saving, onSave }: {
  profile: Profile;
  setProfile: (next: Profile) => void;
  saving: boolean;
  onSave: () => Promise<void> | void;
}) {
  return <SettingsSection
    title="你的学习资料"
    description="用于调整讲解起点，不会作为公开资料或自动写入 Wiki。"
    footer={<button className="primary-button" disabled={saving} onClick={() => void onSave()}><Check size={15} />保存我的资料</button>}
  >
    <SettingsField label="怎么称呼你">
      <input maxLength={60} value={profile.display_name} onChange={(event) => setProfile({ ...profile, display_name: event.target.value })} />
    </SettingsField>
    <SettingsField label="个人简介">
      <textarea rows={5} maxLength={1000} value={profile.profile} onChange={(event) => setProfile({ ...profile, profile: event.target.value })} placeholder="例如：正在学习计算机基础，熟悉 Python。" />
    </SettingsField>
    <SettingsField label="长期学习目标">
      <textarea rows={4} maxLength={500} value={profile.long_term_goal} onChange={(event) => setProfile({ ...profile, long_term_goal: event.target.value })} />
    </SettingsField>
  </SettingsSection>;
}
