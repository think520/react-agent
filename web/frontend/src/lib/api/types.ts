/**
 * HTTP 层的数据契约（2026-10-17 从 lib/api.ts 抽出；纯类型、零行为）。
 */
import type {
  Attribution,
  ChatArtifact,
  PersonalizationRef,
} from "../../types";
import type { ChatStreamEventKind } from "../chatStreamEvents";

/**
 * 资料库文件夹同步的摘要（E17 ①）。
 *
 * 每个数字都要对得上用户能看到的东西：新增 / 更新 / 移除 / 待确认移除 /
 * 跳过（仓库元文件）/ 重复清理 / 失败（含每份的原因）。
 */
export interface KnowledgeSyncSummary {
  ok: boolean;
  scanned_files: number;
  updated_files: number;
  changed_files: number;
  error_files: number;
  errors: { source?: string; error?: string }[];
  extraction_counts: Record<string, number>;
  added_files: string[];
  removed_files: string[];
  duplicates_cleaned: string[];
  pending_removal: string[];
  skipped_files: string[];
  /** 本次扫描看不全（路径读不到，或已登记的来源根此刻不可用）——此时不会移除任何资料。 */
  scan_incomplete: boolean;
  incomplete_reasons: string[];
}

/** 只读文件夹树（E17 ②）。计数是**含子目录**的合计；ignored_here 只列本层。 */
export interface KnowledgeTreeFile {
  type: "file";
  name: string;
  /** 相对资料库根的真实路径（不含盘符，绝不外泄绝对路径）。 */
  path: string;
  size: number;
  modified_at: string;
  indexed: boolean;
  document_id: string | null;
  title: string;
  extraction_status: string | null;
  chunk_count: number;
}

export interface KnowledgeTreeIgnored {
  name: string;
  path: string;
  reason: "repo_metadata" | "unsupported_type";
}

export interface KnowledgeTreeFolder {
  type: "folder";
  name: string;
  path: string;
  children: KnowledgeTreeFolder[];
  files: KnowledgeTreeFile[];
  material_count: number;
  indexed_count: number;
  ignored_count: number;
  ignored_here: KnowledgeTreeIgnored[];
}

export interface KnowledgeTree extends KnowledgeTreeFolder {
  /** 库名，只用于展示。 */
  name: string;
}

/** 一条归档记录（E17 ③）：文件被移到了哪里，以及怎么放回去。 */
export interface ArchivedEntry {
  entry_id: string;
  archived_at: string;
  reason: string;
  document_id: string;
  source: string;
  title: string;
  original_path: string;
  archived_path: string;
  size: number;
}

/** 一条整理建议（E17 ⑤）：只提议，等用户确认才执行。 */
export interface OrganizationProposal {
  kind: string;
  title: string;
  reason: string;
  items: string[];
  suggested_folder: string;
  requires_confirmation: boolean;
  /** "model" = 模型提的，"rules" = 确定性规则提的（E17 ⑤）。 */
  source?: string;
}

/** 整理建议的来源与降级原因（E17 ⑤）：界面必须如实说明是谁提的。 */
export interface OrganizationProposalResult {
  ok: boolean;
  proposals: OrganizationProposal[];
  source: string;
  degraded: string;
}

/** 服务端记下的一步整理（E17 ⑤）：界面刷新后据此决定还能不能撤销。 */
export interface OrganizationBatch {
  batch_id: string;
  created_at: string;
  target_folder: string;
  moves: { document_id: string; from: string; to: string; state?: string; error?: string }[];
  /** planned / applying / applied / partial / failed / partial_undo（F02 的"先写计划"）。 */
  status?: string;
}

/** E8：一次导入里**单个文件**的结果（失败清单 UI 按它逐条说明）。 */
export interface ImportBatchResult {
  filename: string;
  status: string;
  path?: string;
  searchable?: boolean;
  chunks?: number;
  extraction?: string | null;
  reason?: string;
  existing?: string;
}




export type ChatStreamEventKindMatchesUnion =
  ChatStreamEvent["event"] extends ChatStreamEventKind
    ? ChatStreamEventKind extends ChatStreamEvent["event"]
      ? true
      : { missingUnionMember: Exclude<ChatStreamEventKind, ChatStreamEvent["event"]> }
    : { missingKindConstant: Exclude<ChatStreamEvent["event"], ChatStreamEventKind> };

interface StreamFrameMeta {
  stream_id?: string;
  seq?: number;
}

export type ChatStreamEvent =
  | { event: "run_started"; data: { run_id: string; chat_session_id: string } & StreamFrameMeta }
  | { event: "message_delta"; data: { content: string; call_role?: "narration" | "finish" } & StreamFrameMeta }
  | { event: "status"; data: { phase: string; message: string; tool_name?: string; elapsed?: number } & StreamFrameMeta }
  | { event: "citation"; data: { attribution: Attribution } & StreamFrameMeta }
  | { event: "chat_artifact"; data: { artifact: ChatArtifact } & StreamFrameMeta }
  | { event: "personalization"; data: { references: PersonalizationRef[] } & StreamFrameMeta }
  | { event: "answer_truncated"; data: { continuing: boolean; continues: number } & StreamFrameMeta }
  | { event: "run_completed"; data: { chat_session_id: string; termination_reason: string } & StreamFrameMeta }
  | { event: "run_failed"; data: { error: { code: string; message: string } } & StreamFrameMeta };

