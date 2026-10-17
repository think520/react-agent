import type { UserPreferences } from "../../../types";
import { SettingsRow, SettingsSection, SettingsSegmented, SettingsToggle } from "../SettingsPrimitives";

type Appearance = UserPreferences["appearance"];

/** 设置 · 界面与阅读（2026-10-17 S2；改动即时保存，与迁移前一致）。 */
export function AppearanceSection({ appearance, patch }: {
  appearance: Appearance;
  patch: (patch: Record<string, unknown>) => void;
}) {
  return <>
    <SettingsSection title="阅读排版" description="高频操作仍使用系统黑体，正文阅读可以选择今楷或宋体。">
      <SettingsRow label="阅读字体">
        <SettingsSegmented label="阅读字体" value={appearance.reading_font} onChange={(value) => patch({ appearance: { reading_font: value } })} options={[{ value: "jin-kai", label: "今楷" }, { value: "noto-serif", label: "宋体" }]} />
      </SettingsRow>
      <SettingsRow label="正文字号">
        <SettingsSegmented label="正文字号" value={appearance.body_font_size} onChange={(value) => patch({ appearance: { body_font_size: value } })} options={[15, 16, 17, 18].map((value) => ({ value, label: String(value) }))} />
      </SettingsRow>
      <SettingsRow label="内容宽度">
        <SettingsSegmented label="内容宽度" value={appearance.content_width} onChange={(value) => patch({ appearance: { content_width: value } })} options={[{ value: 640, label: "窄" }, { value: 720, label: "标准" }, { value: 800, label: "宽" }]} />
      </SettingsRow>
    </SettingsSection>
    <SettingsSection title="界面感受">
      <SettingsRow label="纸张纹理" hint="保持轻微，不影响正文对比度">
        <SettingsToggle label="纸张纹理" checked={appearance.paper_texture} onChange={(value) => patch({ appearance: { paper_texture: value } })} />
      </SettingsRow>
      <SettingsRow label="会话列表密度">
        <SettingsSegmented label="会话列表密度" value={appearance.session_density} onChange={(value) => patch({ appearance: { session_density: value } })} options={[{ value: "comfortable", label: "舒展" }, { value: "compact", label: "紧凑" }]} />
      </SettingsRow>
      <SettingsRow label="减少动态效果">
        <SettingsToggle label="减少动态效果" checked={appearance.motion === "reduced"} onChange={(value) => patch({ appearance: { motion: value ? "reduced" : "system" } })} />
      </SettingsRow>
    </SettingsSection>
  </>;
}
