/**
 * LibraryPage 的左侧文件树栏（2026-10-17 M2 store-lift 第 5 步 · 分块搬出）。
 * 只负责渲染：文件夹树 + 原文命中 + 整理建议入口；所有动作由页面通过 props 传入。
 */
import { FolderOpen, Search } from "lucide-react";

import { LibraryTree } from "../../components/LibraryTree";
import type { KnowledgeTree } from "../../lib/api";
import type { ArchivedEntry, OrganizationBatch, OrganizationProposal } from "../../lib/api";
import type { NavigateFunction } from "react-router-dom";
import { readerLocation } from "../../lib/documentLinks";
import type { createLibraryMaterialActions } from "./libraryActions";

type MaterialActions = ReturnType<typeof createLibraryMaterialActions>;

export interface LibraryTreePanelProps {
  archive: ArchivedEntry[];
  restoreArchived: MaterialActions["restoreArchived"];
  tree: KnowledgeTree;
  documentQuery: string;
  setDocumentQuery: (value: string) => void;
  hits: Array<{ chunk_id: string; document_id: string; collection?: string; title?: string; source?: string; text?: string }>;
  navigate: NavigateFunction;
  collection: "material" | "wiki";
  selectedFolder: string;
  setSelectedFolder: (value: string) => void;
  selectedId: string | null;
  selectDocument: MaterialActions["selectDocument"];
  moveDocument: MaterialActions["moveDocument"];
  archiveDocument: MaterialActions["archiveDocument"];
  createFolder: MaterialActions["createFolder"];
  deleteFolder: MaterialActions["deleteFolder"];
  organizeProposals: OrganizationProposal[] | null;
  organizeBusy: boolean;
  organizeSource: string;
  organizeDegraded: string;
  organizePending: OrganizationBatch | null;
  loadOrganizeProposals: MaterialActions["loadOrganizeProposals"];
  loadAiProposals: MaterialActions["loadAiProposals"];
  applyProposal: MaterialActions["applyProposal"];
  undoOrganize: MaterialActions["undoOrganize"];
}

export function LibraryTreePanel(props: LibraryTreePanelProps) {
  const {
    tree,
    documentQuery,
    setDocumentQuery,
    hits,
    navigate,
    collection,
    selectedFolder,
    setSelectedFolder,
    selectedId,
    selectDocument,
    moveDocument,
    archiveDocument,
    createFolder,
    deleteFolder,
    organizeProposals,
    organizeBusy,
    organizeSource,
    organizeDegraded,
    organizePending,
    loadOrganizeProposals,
    loadAiProposals,
    applyProposal,
    undoOrganize,
    archive,
    restoreArchived,
  } = props;

  return (
  <aside className="library-tree-pane" aria-label="资料库文件夹">
    <div className="rail-label"><FolderOpen size={15} />文件夹 <span>{tree.material_count}</span></div>
    
    <label className="document-search"><Search size={14} /><input value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} placeholder="搜索资料" aria-label="搜索资料" /></label>
    {hits.length > 0 && (
      <div className="document-hits" aria-label="原文命中">
        {hits.map((hit) => (
          <button
            key={hit.chunk_id}
            className="document-hit"
            type="button"
            title={hit.text || ""}
            onClick={() =>
              navigate(
                readerLocation({
                  document_id: hit.document_id,
                  collection: hit.collection ?? collection,
                  chunk_id: hit.chunk_id,
                }) || "/library",
              )
            }
          >
            <Search size={13} />
            <span>
              <strong>{hit.title || hit.source}</strong>
              <small>{(hit.text || "").replace(/\s+/g, " ").slice(0, 56)}</small>
            </span>
          </button>
        ))}
      </div>
    )}
    <LibraryTree
      tree={tree}
      query={documentQuery}
      selectedFolder={selectedFolder}
      onSelectFolder={setSelectedFolder}
      activeDocumentId={selectedId}
      onOpenDocument={(documentId) => selectDocument(documentId)}
      onMoveDocument={(documentId, path) => void moveDocument(documentId, path)}
      onArchiveDocument={(documentId, title) => void archiveDocument(documentId, title)}
      onCreateFolder={(path) => void createFolder(path)}
      onDeleteFolder={(path) => void deleteFolder(path)}
    />
    {collection === "material" && (
      <details className="library-organize">
        <summary>整理建议</summary>
        <div>
          {organizeProposals === null ? (
            <>
              <button className="quiet-button" type="button" disabled={organizeBusy} onClick={() => void loadOrganizeProposals()}>
                看看有什么可以整理的
              </button>
              <button className="quiet-button" type="button" disabled={organizeBusy} onClick={() => void loadAiProposals()}>
                让 AI 归类
              </button>
            </>
          ) : organizeProposals.length === 0 ? (
            <p className="text-faint">资料库已经很整齐了。</p>
          ) : (
            <>
            <p className="text-faint">
              {organizeSource === "model"
                ? "AI 提议 —— 执行前由你确认，执行后可一键撤销。"
                : organizeDegraded
                  ? "模型这次没能参与，下面是规则建议 —— 执行前由你确认，执行后可一键撤销。"
                  : "规则建议 —— 执行前由你确认，执行后可一键撤销。"}
            </p>
            {organizeProposals.map((proposal) => (
              <div key={proposal.kind}>
                <strong>{proposal.title}（{proposal.items.length} 份）</strong>
                <p>{proposal.reason}</p>
                <ul>
                  {proposal.items.slice(0, 8).map((item) => <li key={item}>{item}</li>)}
                  {proposal.items.length > 8 && <li className="text-faint">…… 其余 {proposal.items.length - 8} 份</li>}
                </ul>
                <button className="quiet-button" type="button" disabled={organizeBusy} onClick={() => void applyProposal(proposal)}>
                  收进「{proposal.suggested_folder}」
                </button>
              </div>
            ))}
            </>
          )}
        </div>
      </details>
    )}
    {collection === "material" && organizePending && (
      <div className="library-organize-undo">
        <button className="quiet-button" type="button" disabled={organizeBusy} onClick={() => void undoOrganize()}>
          撤销这一步整理
        </button>
        <small className="text-faint">
          {organizePending.status && organizePending.status !== "applied"
            ? `上一次整理未完成（${organizePending.moves.length} 项），可以撤销已经搬走的部分`
            : `上一步：${organizePending.moves.length} 份资料收进「${organizePending.target_folder}」`}
        </small>
      </div>
    )}
    {archive.length > 0 && (
      <details className="library-archive">
        <summary>已归档 {archive.length} 份</summary>
        <ul>
          {archive.slice(0, 30).map((entry) => (
            <li key={entry.entry_id}>
              <span title={entry.original_path}>{entry.title || entry.original_path}</span>
              <button className="quiet-button" type="button" onClick={() => void restoreArchived(entry.entry_id)}>
                恢复
              </button>
            </li>
          ))}
        </ul>
      </details>
    )}
  </aside>
  );
}
