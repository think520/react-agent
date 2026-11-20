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
  session_not_found: "这个会话已经不在了（可能在别处被删除）。从左侧列表重新打开，或开始一个新会话。",
  session_corrupt: "这个会话文件损坏了，无法打开。其它会话不受影响；可以从左侧删除它。",
  session_ambiguous: "有不止一个会话匹配，请从左侧列表直接点开要的那一个。",
  session_delete_failed: "会话文件没能删除（可能被别的程序占用）。稍后再试一次。",
  knowledge_item_not_found: "这条个人知识已经不在了（可能在别处被删除）。刷新列表看看当前还有哪些。",
  backup_not_found: "找不到这个备份文件，可能已被移动或删除。",
  backup_corrupt: "备份包校验未通过（文件可能损坏或被修改），本次恢复已取消，原资料未受影响。",
  backup_invalid: "这不是有效的 Bobodan 备份包（或包含不允许导入的敏感文件），已拒绝恢复。",
  restore_target_not_empty: "恢复目标文件夹不是空的，请换一个空白目录，以免覆盖已有资料。",
  restore_target_invalid: "恢复目标目录不能与应用数据目录重叠，请选择单独的资料库文件夹。",
  restore_failed: "恢复过程出错，已自动回滚到恢复前状态；原资料与配置未受破坏。",
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

/**
 * 给用户看的一句话：有可行动提示就用提示（它说清了下一步），否则用后端文案，再否则用兜底。
 * 2026-11-11：后端补了结构化 code，但界面多处只显示 `reason.message`，提示从未上屏。
 */
export function userMessageFor(reason: unknown, fallback: string): string {
  const hint = errorHint(errorCodeOf(reason));
  if (hint) return hint;
  return reason instanceof Error && reason.message ? reason.message : fallback;
}
