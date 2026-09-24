import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, FolderPlus, MoreHorizontal } from "lucide-react";

import type { KnowledgeTreeFile, KnowledgeTreeFolder } from "../lib/api";

/**
 * 只读 + 写操作的文件夹树（E17 ② ③）。
 *
 * 设计：`docs/LIBRARY_TREE_DESIGN.md` §3.3 / §3.5
 * - 文件夹行：资料数 + 「N 份未提取」；本层被忽略的文件可展开核对；
 * - 文件行：状态点 + 悬浮细节；行尾 ⋯ 提供重命名/移动到/归档；
 * - 树顶可新建文件夹；文件夹行 ⋯ 提供「删文件夹（只删容器）」；
 * - 展开状态记忆在 localStorage。
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

export interface TreeActions {
  onMoveDocument?: (documentId: string, newRelativePath: string) => void;
  onArchiveDocument?: (documentId: string, title: string) => void;
  onCreateFolder?: (relativePath: string) => void;
  onDeleteFolder?: (relativePath: string) => void;
}

export function LibraryTree({
  tree,
  query = "",
  selectedFolder,
  onSelectFolder,
  activeDocumentId,
  onOpenDocument,
  onMoveDocument,
  onArchiveDocument,
  onCreateFolder,
  onDeleteFolder,
}: {
  tree: KnowledgeTreeFolder;
  query?: string;
  selectedFolder: string;
  onSelectFolder: (path: string) => void;
  activeDocumentId?: string | null;
  onOpenDocument: (documentId: string) => void;
} & TreeActions) {
  const [expanded, setExpanded] = useState<Set<string>>(() => loadExpanded());
  const [createValue, setCreateValue] = useState("");

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
    <>
      {onCreateFolder && (
        <label className="library-tree-create">
          <FolderPlus size={14} />
          <input
            aria-label="新建文件夹"
            placeholder={selectedFolder ? `在 ${selectedFolder} 下新建…` : "新建文件夹…"}
            value={createValue}
            onChange={(event) => setCreateValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              const value = createValue.trim();
              if (!value) return;
              onCreateFolder(selectedFolder ? `${selectedFolder}/${value}` : value);
              setCreateValue("");
            }}
          />
        </label>
      )}
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
            onMoveDocument={onMoveDocument}
            onArchiveDocument={onArchiveDocument}
            onDeleteFolder={onDeleteFolder}
          />
        ))}
        {visible.files.map((file) => (
          <TreeFile
            key={file.path}
            file={file}
            depth={0}
            active={activeDocumentId === file.document_id}
            onOpenDocument={onOpenDocument}
            onMoveDocument={onMoveDocument}
            onArchiveDocument={onArchiveDocument}
          />
        ))}
      </ul>
    </>
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
  onMoveDocument,
  onArchiveDocument,
  onDeleteFolder,
}: {
  folder: KnowledgeTreeFolder;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  selectedFolder: string;
  onSelectFolder: (path: string) => void;
  activeDocumentId?: string | null;
  onOpenDocument: (documentId: string) => void;
} & TreeActions) {
  const open = expanded.has(folder.path);
  const files = collectFiles(folder);
  const pending = files.filter((file) => treeStatusTone(file) !== "complete").length;
  const selected = selectedFolder === folder.path;
  const [renaming, setRenaming] = useState<string | null>(null);

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
        {renaming === "folder" ? (
          <input
            className="library-tree-rename"
            autoFocus
            defaultValue={folder.name}
            aria-label={`重命名 ${folder.name}`}
            onBlur={() => setRenaming(null)}
            onKeyDown={(event) => {
              const value = (event.target as HTMLInputElement).value.trim();
              if (event.key === "Escape") setRenaming(null);
              if (event.key === "Enter" && value && value !== folder.name) {
                const parent = folder.path.includes("/") ? folder.path.slice(0, folder.path.lastIndexOf("/")) : "";
                onMoveDocument?.(folder.path, parent ? `${parent}/${value}` : value);
                setRenaming(null);
              }
            }}
          />
        ) : (
          <button className="library-tree-name" type="button" onClick={() => onSelectFolder(folder.path)}>
            {open ? <FolderOpen size={15} /> : <Folder size={15} />}
            <span>{folder.name}</span>
          </button>
        )}
        <span className="library-tree-meta">
          {folder.material_count} 份
          {pending > 0 && <em> · {pending} 份未提取</em>}
        </span>
        {onDeleteFolder && (
          <details className="library-tree-actions">
            <summary aria-label={`${folder.name} 的更多操作`}><MoreHorizontal size={14} /></summary>
            <div>
              <button type="button" onClick={() => onDeleteFolder(folder.path)}>
                删文件夹（资料移回库根，一份都不删）
              </button>
            </div>
          </details>
        )}
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
              onMoveDocument={onMoveDocument}
              onArchiveDocument={onArchiveDocument}
              onDeleteFolder={onDeleteFolder}
            />
          ))}
          {folder.files.map((file) => (
            <TreeFile
              key={file.path}
              file={file}
              depth={depth + 1}
              active={activeDocumentId === file.document_id}
              onOpenDocument={onOpenDocument}
              onMoveDocument={onMoveDocument}
              onArchiveDocument={onArchiveDocument}
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
  onMoveDocument,
  onArchiveDocument,
}: {
  file: KnowledgeTreeFile;
  depth: number;
  active: boolean;
  onOpenDocument: (documentId: string) => void;
} & TreeActions) {
  const tone = treeStatusTone(file);
  const [renaming, setRenaming] = useState(false);
  const detail = [
    file.indexed ? `${file.chunk_count} 个片段` : "还没同步进索引",
    file.modified_at ? `更新于 ${new Date(file.modified_at).toLocaleDateString("zh-CN")}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <li role="treeitem" aria-selected={active}>
      <div className={`library-tree-row file ${active ? "active" : ""}`} style={{ paddingLeft: 6 + depth * 14 }}>
        {renaming && file.document_id ? (
          <input
            className="library-tree-rename"
            autoFocus
            defaultValue={file.name}
            aria-label={`重命名 ${file.name}`}
            onBlur={() => setRenaming(false)}
            onKeyDown={(event) => {
              const value = (event.target as HTMLInputElement).value.trim();
              if (event.key === "Escape") setRenaming(false);
              if (event.key === "Enter" && value && value !== file.name) {
                const documentId = file.document_id;
                if (!documentId) return;
                const parent = file.path.includes("/") ? file.path.slice(0, file.path.lastIndexOf("/")) : "";
                onMoveDocument?.(documentId, parent ? `${parent}/${value}` : value);
                setRenaming(false);
              }
            }}
          />
        ) : (
          <button
            className="library-tree-open"
            type="button"
            title={detail}
            disabled={!file.document_id}
            onClick={() => file.document_id && onOpenDocument(file.document_id)}
          >
            <FileText size={15} />
            <span className="library-tree-name">{file.name}</span>
            <span className={`library-tree-dot ${tone}`} title={TONE_LABEL[tone]} aria-label={TONE_LABEL[tone]} />
          </button>
        )}
        {(onMoveDocument || onArchiveDocument) && file.document_id && (
          <details className="library-tree-actions">
            <summary aria-label={`${file.name} 的更多操作`}><MoreHorizontal size={14} /></summary>
            <div>
              {onMoveDocument && <button type="button" onClick={() => setRenaming(true)}>重命名</button>}
              {onArchiveDocument && (
                <button type="button" onClick={() => onArchiveDocument(file.document_id as string, file.name)}>
                  归档（可从「已归档」恢复）
                </button>
              )}
            </div>
          </details>
        )}
      </div>
    </li>
  );
}
