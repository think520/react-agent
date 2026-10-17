/** library 域的 API 方法（2026-10-17 从 lib/api.ts 逐块搬出，行为不变）。 */
import { json, request } from "../http";
import { } from "../transport";
import type {
  DocumentSection,
  DocumentSummary,
  DocumentImpact,
  LibrarySummary,
  LibraryMigrationPreview,
} from "../../../types";
import type { } from "../../chatStreamEvents";
import type {
  KnowledgeSyncSummary, KnowledgeTree, ImportBatchResult, ArchivedEntry,
  OrganizationProposalResult, OrganizationBatch, } from "../types";
import type { } from "../transport";

export const libraryApi = {
  libraries: () => request<{ active_library_id: string | null; libraries: LibrarySummary[] }>("/api/libraries"),
  createLibrary: (name: string, parentPath: string) => request<LibrarySummary>(
    "/api/libraries",
    json({ name, parent_path: parentPath }),
  ),
  openLibrary: (path: string) => request<LibrarySummary>("/api/libraries/open", json({ path })),
  previewLibraryMigration: (path: string) => request<LibraryMigrationPreview>(
    "/api/libraries/migrate/preview",
    json({ path }),
  ),
  migrateLibrary: (path: string, name: string) => request<{
    library: LibrarySummary;
    preview: LibraryMigrationPreview;
    sync: Record<string, unknown>;
  }>("/api/libraries/migrate", json({ path, name })),
  activateLibrary: (id: string) => request<LibrarySummary>(
    `/api/libraries/${encodeURIComponent(id)}/activate`,
    { method: "POST" },
  ),
  /** 只读文件夹树（E17 ②）：真实文件夹 + 资料徽章 + 已忽略计数。 */
  /** 新建文件夹 / 删文件夹（只删容器）/ 重命名移动（E17 ③）。 */
  /** 整理建议：只提议，不动文件（E17 ⑤）。 */
  organizationProposals: () => request<OrganizationProposalResult>(
    "/api/kb/organize/proposals",
  ),
  /** 让模型归类（E17 ⑤）：仍然只提议，**一份文件都不动**，执行前还要用户确认。 */
  aiOrganizationProposals: () => request<OrganizationProposalResult>(
    "/api/kb/organize/proposals",
    json({ use_model: true }),
  ),
  applyOrganization: (items: string[], targetFolder: string) => request<{
    ok: boolean;
    moved: { document_id: string; from: string; to: string }[];
    /** 部分失败时：没搬成的那几项（F07 —— 界面必须如实说清楚）。 */
    failed?: { document_id?: string; from: string; to: string; state?: string; error?: string }[];
    batch_id: string;
    partial?: boolean;
  }>("/api/kb/organize/apply", json({ items, target_folder: targetFolder })),
  /** 还有没有一步可以撤销（刷新页面后仍要知道）。 */
  organizationState: () => request<{ ok: boolean; pending_undo: OrganizationBatch | null }>(
    "/api/kb/organize/state",
  ),
  /** 不带清单时撤销服务端台账里的最后一步（刷新 / 重启后依然可撤销）。 */
  undoOrganization: (moves?: { document_id: string; from: string; to: string }[]) => request<{
    ok: boolean;
    restored: string[];
    /** 原位已经有文件、因此**没有**覆盖的那些项（F03）。 */
    skipped?: { from: string; to: string; reason: string }[];
  }>("/api/kb/organize/undo", json(moves ? { moves } : {})),
  createFolder: (path: string) => request<{ ok: boolean; folder: { name: string; path: string } }>(
    "/api/kb/folders",
    json({ path }),
  ),
  deleteFolder: (path: string) => request<{ ok: boolean; moved: string[]; kept_directory: boolean }>(
    "/api/kb/folders/delete",
    json({ path, mode: "ungroup" }),
  ),
  moveDocument: (documentId: string, path: string) => request<{
    ok: boolean;
    migration: { document_id: string; new_source: string; relative_path: string };
  }>(`/api/kb/documents/${encodeURIComponent(documentId)}/move`, json({ path })),
  /** 已归档的资料（归档只是移走，永远可以恢复）。 */
  knowledgeArchive: () => request<{ ok: boolean; entries: ArchivedEntry[] }>("/api/kb/archive"),
  restoreArchived: (entryId: string) => request<{ ok: boolean; restored: ArchivedEntry }>(
    `/api/kb/archive/${encodeURIComponent(entryId)}/restore`,
    { method: "POST" },
  ),
  knowledgeTree: () => request<{ ok: boolean; tree: KnowledgeTree }>("/api/kb/tree"),
  syncLibrary: (id: string) => request<KnowledgeSyncSummary>(
    `/api/libraries/${encodeURIComponent(id)}/sync`,
    { method: "POST" },
  ),
  unregisterLibrary: (id: string) => request<{ unregistered: boolean }>(
    `/api/libraries/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  ),
  documents: async (collection: "all" | "material" | "wiki" = "all") => (
    await request<{ documents: DocumentSummary[] }>(`/api/kb/documents?collection=${collection}`)
  ).documents,
  document: (id: string) => request<{ document: DocumentSummary; sections: DocumentSection[] }>(
    `/api/kb/documents/${encodeURIComponent(id)}`,
  ),
  documentContent: (id: string) => request<{ document: DocumentSummary; content: string; editable: boolean; content_hash: string }>(
    `/api/kb/documents/${encodeURIComponent(id)}/content`,
  ),
  editDocument: (id: string, body: { content: string; expected_hash?: string | null; conflict_action?: "overwrite" | "abandon" | "save_as_new" }) => request<{
    document_id: string; content_hash: string; conflict?: string | null; sync?: Record<string, unknown>;
  }>(
    `/api/kb/documents/${encodeURIComponent(id)}/content`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  ),
  documentVersions: (id: string) => request<{ versions: Array<{ id: string; created_at: string; content_hash: string }> }>(
    `/api/kb/documents/${encodeURIComponent(id)}/versions`,
  ),
  rollbackDocument: (id: string, versionId: string) => request<{ document_id: string; version_id: string; sync?: Record<string, unknown> }>(
    `/api/kb/documents/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/rollback`,
    { method: "POST" },
  ),
  createDocumentProposal: (id: string, body: { instruction: string; provider?: string | null }) => request<{ proposal: import("../../../types").DocumentProposal }>(
    `/api/kb/documents/${encodeURIComponent(id)}/proposals`,
    json(body),
  ),
  createNewDocumentProposal: (body: { title: string; content: string; reason?: string }) => request<{ proposal: import("../../../types").DocumentProposal }>(
    "/api/kb/proposals",
    json(body),
  ),
  documentProposal: (id: string) => request<{ proposal: import("../../../types").DocumentProposal }>(
    `/api/kb/proposals/${encodeURIComponent(id)}`,
  ),
  applyDocumentProposal: (id: string) => request<{ proposal: import("../../../types").DocumentProposal }>(
    `/api/kb/proposals/${encodeURIComponent(id)}/apply`,
    { method: "POST" },
  ),
  undoDocumentProposal: (id: string) => request<{ proposal: import("../../../types").DocumentProposal }>(
    `/api/kb/proposals/${encodeURIComponent(id)}/undo`,
    { method: "POST" },
  ),
  deleteDocument: (id: string) => request<{ document_id: string }>(
    `/api/kb/documents/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  ),
  updateSessionProvider: (id: string, provider: string, model?: string) => request<{ provider_name: string; model_name: string | null }>(
    `/api/chat/sessions/${encodeURIComponent(id)}/provider`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider, model: model || null }) },
  ),
  documentImpact: (id: string) => request<DocumentImpact>(
    `/api/kb/documents/${encodeURIComponent(id)}/impact`,
  ),
  importDocuments: async (files: File[], duplicateStrategy: "keep_existing" | "save_copy" = "keep_existing") => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("duplicate_strategy", duplicateStrategy);
    return request<{
      imported: string[];
      duplicates?: Array<{ filename: string; existing: string; reason: string }>;
      /** 字节已经在库里、这次是**补做索引**的那些（F04）。 */
      pending?: Array<{ filename: string; existing: string; reason: string }>;
      rejected: unknown[];
      /** E8：用户中途取消了这次导入（已收下的保持收下）。 */
      cancelled?: boolean;
      /** 本次上传的逐文件结果（F09：批次计数只认它）。 */
      results?: ImportBatchResult[];
      /** 全库增量同步：单独展示，不当批次计数用。 */
      library_sync: KnowledgeSyncSummary;
    }>(
      "/api/kb/import",
      { method: "POST", body: form },
    );
  },
  /** E8：开始一次**可观察、可取消**的导入（返回 import_id，进度靠轮询）。 */
  startImport: async (files: File[], duplicateStrategy: "keep_existing" | "save_copy" = "keep_existing") => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("duplicate_strategy", duplicateStrategy);
    return request<{ ok: boolean; import_id: string }>(
      "/api/kb/imports",
      { method: "POST", body: form },
    );
  },
  /** E8：读一次导入进度快照（终态时带 result）。 */
  importStatus: (importId: string) => request<{
    import_id: string;
    status: "running" | "completed" | "failed" | "cancelled";
    phase: string;
    files_total: number;
    files_done: number;
    current: string;
    sources_total: number;
    sources_done: number;
    error: string;
    result: {
      imported: string[];
      duplicates?: Array<{ filename: string; existing: string; reason: string }>;
      rejected: unknown[];
      pending?: unknown[];
      cancelled?: boolean;
      results?: ImportBatchResult[];
      library_sync: KnowledgeSyncSummary;
    } | null;
  }>(`/api/kb/imports/${encodeURIComponent(importId)}`),
  /** E8：协作式取消（在文件边界生效，已收下的保持收下）。 */
  cancelImport: (importId: string) => request<{ ok: boolean; cancelled: boolean }>(
    `/api/kb/imports/${encodeURIComponent(importId)}/cancel`,
    { method: "POST" },
  ),  /** W1 E2：新建资料库的默认值 —— 由后端给，前端不再自己拼路径。 */
  libraryDefaults: () => request<{ name: string; parent_path: string; root_path: string }>(
    "/api/libraries/defaults",
  ),
  /** W1 E2：把「父目录 + 名称」翻译成将来真正创建的根目录（与创建走同一套规则）。 */
  libraryRootPreview: (name: string, parent: string) => request<{
    name: string; parent_path: string; root_path: string;
  }>(`/api/libraries/root-preview?name=${encodeURIComponent(name)}&parent=${encodeURIComponent(parent)}`),
  /** W1 E4：跳过这个 ask_user 卡片（关闭交互，由调用方随即恢复暂停的 run）。 */
  documentAnchors: (documentId: string) => request<{
    anchors: Array<{
      anchor_id: string; document_id: string; chunk_id: string; quote: string;
      char_start: number | null; char_end: number | null; note: string; created_at: string;
      resolution: { status: string; char_start: number | null; char_end: number | null };
    }>;
    count: number;
  }>(`/api/kb/documents/${encodeURIComponent(documentId)}/anchors`),
  createDocumentAnchor: (
    documentId: string,
    body: { chunk_id?: string; quote: string; char_start?: number | null; char_end?: number | null; note?: string },
  ) => request<{ anchor: { anchor_id: string } }>(
    `/api/kb/documents/${encodeURIComponent(documentId)}/anchors`, json(body),
  ),
  deleteDocumentAnchor: (anchorId: string) => request<{ anchor_id: string }>(
    `/api/kb/anchors/${encodeURIComponent(anchorId)}`, { method: "DELETE" },
  ),
};
