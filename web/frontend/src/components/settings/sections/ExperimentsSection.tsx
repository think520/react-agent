import { SettingsSection } from "../SettingsPrimitives";

/** 设置 · 实验（2026-10-17 S5）：目前没有实验开关，如实说明。 */
export function ExperimentsSection() {
  return <SettingsSection title="实验" description="实验开关默认全部关闭，打开后也随时可以关回去。">
    <p className="settings-empty">暂时没有实验开关。新能力默认走稳定路径；需要灰度时才会出现在这里。</p>
  </SettingsSection>;
}
