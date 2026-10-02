/**
 * W1 E1：把后端的结构化错误码翻译成**下一步动作**。
 *
 * 以前界面只显示后端文案，用户分不清「等一会儿重试就行」「得先去设置里配模型」
 * 「资料库被移动了要重新接入」。这里只写**用户确实有下一步**的 code；
 * 不认识的 code 一律返回空 —— 不编建议（后端文案已经说明了发生了什么）。
 */
const HINTS: Record<string, string> = {
  grading_unavailable: "模型暂时不可用，本次作答没有被记为答错；稍后重试即可。",
  provider_unconfigured: "还没有配置模型服务：到「设置 → 模型服务」填好之后再试。",
  provider_timeout: "模型响应超时了，稍后重试即可；已经生成的内容不会重复。",
  library_unavailable: "当前资料库不可用（可能被移动、改名或删除了）。到「设置 → 资料库」重新接入。",
  library_not_found: "找不到这个资料库了。到「设置 → 资料库」看当前有哪些可用。",
  unsupported_file_type: "这个格式暂时不能索引；支持 Markdown、PDF、Word 和 PowerPoint。",
  document_read_only: "这份资料是只读的（来自原始资料库），可以先另存为笔记再修改。",
  bank_empty: "题库里还没有题。先去资料库读一份材料，再从那里生成练习。",
  target_exists: "目标已存在，换一个名称，或先删掉/移动已有的那个。",
  wiki_page_revision_conflict: "这个页面在别处被改过了。刷新后对比一下，再决定保留哪一版。",
};

export function errorHint(code?: string): string {
  if (!code) return "";
  return HINTS[code] || "";
}

/** 取错误对象上的结构化 code（«ApiError» 有，其它带 code 的错误也认；普通错误返回空）。 */
export function errorCodeOf(reason: unknown): string {
  if (!reason || typeof reason !== "object") return "";
  const code = (reason as { code?: unknown }).code;
  return typeof code === "string" ? code : "";
}
