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
      <p className="settings-model-hint">远程模型只接收你主动提问时构造的上下文；向量索引与个人知识都保存在本机 SQLite 里。</p>
    </SettingsSection>

    <section className="settings-boundary"><ShieldCheck size={20} /><div><strong>本地优先</strong><p>Bobodan 不上传资料库内容，也没有账号体系；卸载前请自行备份应用数据目录。</p></div></section>
  </>;
}
