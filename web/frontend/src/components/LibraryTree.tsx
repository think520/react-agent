import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FileText, FolderOpen, Folder } from "lucide-react";

import type { KnowledgeTreeFile, KnowledgeTreeFolder } from "../lib/api";

/**
 * 只读文件夹树（E17 ②）。
 *
 * 设计：`docs/LIBRARY_TREE_DESIGN.md` §3.3 —— 树建在真实文件系统上：
 * - 文件夹行：资料数 + 「N 份未提取」；本层被忽略的文件可展开核对；
 * - 文件行：状态点（已索引/未提取/失败）+ 悬浮显示 chunk 数与更新时间；
 * - 展开状态记忆在 localStorage，跨会话保留。
 */

const EXPANDED_KEY = "bobodan:library-tree:expanded";

function loadExpanded(): Set<string> {
  try {
    const raw = localStorage.getItem(EXPANDED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : []);
  } catch {
    return new Set();
  }
}

export function collectFiles(tree: KnowledgeTreeFolder): KnowledgeTreeFile[] {
  return [...tree.files, ...tree.children.flatMap(collectFiles)];
}

/**
 * 搜索时的树过滤：命中就保留，并保留命中项的**祖先链**（否则文件会"悬空"）。
 * 与参考项目一致：folders are not a filter, they are a location。
 */
export function filterTree(folder: KnowledgeTreeFolder, query: string): KnowledgeTreeFolder | null {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return folder;
  const children = folder.children
    .map((child) => filterTree(child, needle))
    .filter((child): child is KnowledgeTreeFolder => child !== null);
  const files = folder.files.filter((file) => file.name.toLocaleLowerCase().includes(needle));
  const selfMatches = folder.name.toLocaleLowerCase().includes(needle);
  if (!selfMatches && children.length === 0 && files.length === 0) return null;
  return { ...folder, children, files };
}

/** 状态点：已索引且提取完成是绿的；未索引是灰的；失败是红的；其余是琥珀。 */
export function treeStatusTone(file: KnowledgeTreeFile): "complete" | "pending" | "failed" | "empty" | "unindexed" {
  if (!file.indexed) return "unindexed";
  if (file.extraction_status === "complete") return "complete";
  if (file.extraction_status === "error") return "failed";
  if (file.extraction_status === "empty") return "empty";
  return "pending";
}

const TONE_LABEL: Record<string, string> = {
  complete: "已提取",
  pending: "提取中或待提取",
  failed: "提取失败",
  empty: "没有可提取的文字（扫描件？）",
  unindexed: "还没同步进索引",
};

export function LibraryTree({
  tree,
  query = "",
  selectedFolder,
  onSelectFolder,
  activeDocumentId,
  onOpenDocument,
}: {
  tree: KnowledgeTreeFolder;
  /** 资料名过滤（②：搜索框的上半段结果）；命中项的祖先链会保留。 */
  query?: string;
  selectedFolder: string;
  onSelectFolder: (path: string) => void;
  activeDocumentId?: string | null;
  onOpenDocument: (documentId: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => loadExpanded());

  useEffect(() => {
    try {
      localStorage.setItem(EXPANDED_KEY, JSON.stringify([...expanded]));
    } catch {
      // 存不下不影响使用，只是下次不记得展开状态。
    }
  }, [expanded]);

  const toggle = useCallback((path: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const visible = filterTree(tree, query) ?? { ...tree, children: [], files: [] };

  return (
    <ul className="library-tree" role="tree" aria-label="资料库文件夹">
      {visible.children.map((folder) => (
        <TreeFolder
          key={folder.path}
          folder={folder}
          depth={0}
          expanded={expanded}
          onToggle={toggle}
          selectedFolder={selectedFolder}
          onSelectFolder={onSelectFolder}
          activeDocumentId={activeDocumentId}
          onOpenDocument={onOpenDocument}
        />
      ))}
      {visible.files.map((file) => (
        <TreeFile
          key={file.path}
          file={file}
          depth={0}
          active={activeDocumentId === file.document_id}
          onOpenDocument={onOpenDocument}
        />
      ))}
    </ul>
  );
}

function TreeFolder({
  folder,
  depth,
  expanded,
  onToggle,
  selectedFolder,
  onSelectFolder,
  activeDocumentId,
  onOpenDocument,
}: {
  folder: KnowledgeTreeFolder;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  selectedFolder: string;
  onSelectFolder: (path: string) => void;
  activeDocumentId?: string | null;
  onOpenDocument: (documentId: string) => void;
}) {
  const open = expanded.has(folder.path);
  const files = collectFiles(folder);
  const pending = files.filter((file) => treeStatusTone(file) !== "complete").length;
  const selected = selectedFolder === folder.path;

  return (
    <li role="treeitem" aria-expanded={open} aria-selected={selected}>
      <div className={`library-tree-row folder ${selected ? "selected" : ""}`} style={{ paddingLeft: 6 + depth * 14 }}>
        <button
          className="library-tree-disclosure"
          type="button"
          aria-label={open ? `折叠 ${folder.name}` : `展开 ${folder.name}`}
          onClick={() => onToggle(folder.path)}
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <button className="library-tree-name" type="button" onClick={() => onSelectFolder(folder.path)}>
          {open ? <FolderOpen size={15} /> : <Folder size={15} />}
          <span>{folder.name}</span>
        </button>
        <span className="library-tree-meta">
          {folder.material_count} 份
          {pending > 0 && <em> · {pending} 份未提取</em>}
        </span>
      </div>
      {open && (
        <>
          {folder.ignored_here.length > 0 && (
            <details className="library-tree-ignored">
              <summary style={{ paddingLeft: 24 + depth * 14 }}>
                另有 {folder.ignored_count} 个文件已忽略
              </summary>
              <ul>
                {folder.ignored_here.map((item) => (
                  <li key={item.path}>
                    {item.name}
                    <small>{item.reason === "repo_metadata" ? "仓库元文件" : "不是资料类型"}</small>
                  </li>
                ))}
                {folder.ignored_count > folder.ignored_here.length && (
                  <li className="text-faint">…… 其余 {folder.ignored_count - folder.ignored_here.length} 个未列出</li>
                )}
              </ul>
            </details>
          )}
          {folder.children.map((child) => (
            <TreeFolder
              key={child.path}
              folder={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              selectedFolder={selectedFolder}
              onSelectFolder={onSelectFolder}
              activeDocumentId={activeDocumentId}
              onOpenDocument={onOpenDocument}
            />
          ))}
          {folder.files.map((file) => (
            <TreeFile
              key={file.path}
              file={file}
              depth={depth + 1}
              active={activeDocumentId === file.document_id}
              onOpenDocument={onOpenDocument}
            />
          ))}
        </>
      )}
    </li>
  );
}

function TreeFile({
  file,
  depth,
  active,
  onOpenDocument,
}: {
  file: KnowledgeTreeFile;
  depth: number;
  active: boolean;
  onOpenDocument: (documentId: string) => void;
}) {
  const tone = treeStatusTone(file);
  const detail = [
    file.indexed ? `${file.chunk_count} 个片段` : "还没同步进索引",
    file.modified_at ? `更新于 ${new Date(file.modified_at).toLocaleDateString("zh-CN")}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <li role="treeitem" aria-selected={active}>
      <button
        className={`library-tree-row file ${active ? "active" : ""}`}
        style={{ paddingLeft: 6 + depth * 14 }}
        type="button"
        title={detail}
        disabled={!file.document_id}
        onClick={() => file.document_id && onOpenDocument(file.document_id)}
      >
        <FileText size={15} />
        <span className="library-tree-name">{file.name}</span>
        <span className={`library-tree-dot ${tone}`} title={TONE_LABEL[tone]} aria-label={TONE_LABEL[tone]} />
      </button>
    </li>
  );
}