/**
 * 设置项级搜索（2026-10-17 S5）：搜索的是**每一条设置**，不只是分节名。
 * 命中后切到所属分节并滚动/高亮对应行（见 SettingsDialog.jumpTo）。
 */
export type SettingsTab = "me" | "assistant" | "appearance" | "models" | "rag" | "memory" | "skills" | "security" | "status" | "experiments";

export interface SettingsSearchEntry {
  id: string;
  label: string;
  aliases: string;
  tab: SettingsTab;
}

export const SETTINGS_SEARCH_ENTRIES: SettingsSearchEntry[] = [
  { id: "me-name", label: "怎么称呼你", aliases: "用户 称呼 昵称 名字", tab: "me" },
  { id: "me-profile", label: "个人简介", aliases: "简介 介绍 背景", tab: "me" },
  { id: "me-goal", label: "长期学习目标", aliases: "目标 学习计划", tab: "me" },
  { id: "assistant-name", label: "助手昵称", aliases: "助手 名字 昵称", tab: "assistant" },
  { id: "assistant-teaching", label: "教学方式", aliases: "引导式 讲解式 陪练式 风格", tab: "assistant" },
  { id: "assistant-depth", label: "回答深度", aliases: "简洁 标准 深入", tab: "assistant" },
  { id: "assistant-feedback", label: "反馈方式", aliases: "温和 直接 反馈", tab: "assistant" },
  { id: "appearance-font", label: "阅读字体", aliases: "今楷 宋体 字体", tab: "appearance" },
  { id: "appearance-size", label: "正文字号", aliases: "字号 大小", tab: "appearance" },
  { id: "appearance-width", label: "内容宽度", aliases: "宽度 窄 宽", tab: "appearance" },
  { id: "appearance-texture", label: "纸张纹理", aliases: "纹理 纸张 背景", tab: "appearance" },
  { id: "appearance-density", label: "会话列表密度", aliases: "密度 紧凑 舒展", tab: "appearance" },
  { id: "appearance-motion", label: "减少动态效果", aliases: "动效 动画 减少", tab: "appearance" },
  { id: "models-providers", label: "供应商", aliases: "provider api key 密钥 模板 连接 测试", tab: "models" },
  { id: "models-default", label: "默认模型", aliases: "默认 provider 模型", tab: "models" },
  { id: "models-wiki-discovery", label: "主题发现模型", aliases: "wiki 发现 任务", tab: "models" },
  { id: "models-wiki-drafting", label: "页面撰写模型", aliases: "wiki 撰写 任务", tab: "models" },
  { id: "models-wiki-mode", label: "默认整理方式", aliases: "整理 建档 深度", tab: "models" },
  { id: "models-budget", label: "预算", aliases: "请求上限 token 额度", tab: "models" },
  { id: "models-usage", label: "AI 用量", aliases: "用量 token 请求 费用", tab: "models" },
  { id: "models-search-permission", label: "联网权限", aliases: "联网 搜索 权限", tab: "models" },
  { id: "models-search-provider", label: "搜索供应商", aliases: "tavily exa 自动", tab: "models" },
  { id: "models-jina", label: "Jina Reader 后备", aliases: "jina 后备 读取", tab: "models" },
  { id: "rag-status", label: "检索状态", aliases: "rag 检索 索引 降级", tab: "rag" },
  { id: "rag-glossary", label: "术语词汇表", aliases: "hybrid fts_only unavailable 目录", tab: "rag" },
  { id: "rag-eval", label: "评测与降级可见性", aliases: "评测 基线 用例", tab: "rag" },
  { id: "memory-enabled", label: "启用学习记忆", aliases: "记忆 个性化 开关", tab: "memory" },
  { id: "memory-knowledge", label: "个人知识", aliases: "知识 候选 管理", tab: "memory" },
  { id: "memory-migrate", label: "旧版知识图谱迁移", aliases: "迁移 旧数据 json", tab: "memory" },
  { id: "memory-boundary", label: "本地数据边界", aliases: "隐私 本地 只读", tab: "memory" },
  { id: "skills-list", label: "Web 安全 Skills", aliases: "技能 skills 命令", tab: "skills" },
  { id: "security-keys", label: "密钥存储", aliases: "api key 密钥 存储 位置", tab: "security" },
  { id: "security-logs", label: "日志与诊断", aliases: "日志 诊断 元数据 遥测", tab: "security" },
  { id: "security-boundary", label: "平台边界", aliases: "上传 本地优先 隐私", tab: "security" },
  { id: "status-runtime", label: "运行状态", aliases: "后端 索引 版本 状态", tab: "status" },
  { id: "status-version", label: "版本", aliases: "版本 更新 about", tab: "status" },
  { id: "experiments-list", label: "实验开关", aliases: "实验 预览", tab: "experiments" },
];

export function searchSettings(query: string): SettingsSearchEntry[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [];
  return SETTINGS_SEARCH_ENTRIES.filter((entry) => (entry.label + " " + entry.aliases).toLocaleLowerCase().includes(needle)).slice(0, 12);
}
