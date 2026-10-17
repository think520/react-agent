import type { SettingsSummary, UserPreferences } from "../../../types";
import { SettingsRow, SettingsSection, SettingsToggle } from "../SettingsPrimitives";

/** 设置 · Skills（2026-10-17 S5：迁移到设计系统，行为不变）。 */
export function SkillsSection({ skills, preferences, patch }: {
  skills: SettingsSummary["skills"];
  preferences: UserPreferences;
  patch: (patch: Record<string, unknown>) => void;
}) {
  return <SettingsSection title="Web 安全 Skills" description="这里只显示浏览器运行时能够完整执行的学习技能。">
    {skills.length ? skills.map((skill) => (
      <SettingsRow key={skill.name} label={skill.name} hint={skill.description + " · 能力：" + skill.capabilities.join("、") + " · 来源：" + skill.source}>
        <SettingsToggle
          label={skill.name + " 技能"}
          checked={preferences.skills.enabled_names.includes(skill.name)}
          onChange={(value) => {
            const names = value ? [...preferences.skills.enabled_names, skill.name] : preferences.skills.enabled_names.filter((item) => item !== skill.name);
            patch({ skills: { enabled_names: names } });
          }}
        />
      </SettingsRow>
    )) : <p className="settings-empty">当前没有可用于 Web 的 Skills。</p>}
  </SettingsSection>;
}
