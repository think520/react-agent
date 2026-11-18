import { ShieldCheck } from "lucide-react";

import { SettingsSection } from "../SettingsPrimitives";

/** 设置 · 安全与隐私（2026-10-17 S5）：只陈述事实，不放假开关。 */
export function SecuritySection() {
  return <>
    <SettingsSection title="密钥存储" description="API key 明文保存在本地应用数据目录的 provider.json 里，不会写入资料库或日志。">
      <p className="settings-model-hint">这是刻意的取舍：Bobodan 是本地优先应用，不需要额外服务端保存密钥；换机器时请重新填写，或自行备份该文件。</p>
    </SettingsSection>

    <SettingsSection title="日志与诊断" description="只记录请求元数据（时间、模型、token 数、错误码），不保存提示词或资料正文。">
      <p className="settings-model-hint">用量记录可在「AI 与模型 → AI 用量」里查看；没有遥测上报通道，数据不会离开本机。</p>
    </SettingsSection>

    <SettingsSection title="平台边界" description="原始资料只读；任何移动、重命名都在你确认后执行，且可一键撤销。">
      <p className="settings-model-hint">远程模型仅在你主动发起请求时接收本次构造的上下文。联网研究会把搜索词发送给所配置的搜索服务；使用远程 embedding 时，用于索引的文本片段也会发送给对应服务。</p>
    </SettingsSection>

    <section className="settings-boundary"><ShieldCheck size={20} /><div><strong>本地优先</strong><p>不会批量上传整个资料库；按 Provider、embedding、联网研究和 MCP 配置，本次上下文或处理所需内容可能发送到对应远程服务。应用数据保存在本机；卸载前请自行备份。</p></div></section>
  </>;
}
