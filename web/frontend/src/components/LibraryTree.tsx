import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, FolderPlus, MoreHorizontal } from "lucide-react";

import type { KnowledgeTreeFile, KnowledgeTreeFolder } from "../lib/api";
import { DesktopMenu, type DesktopMenuItem } from "../ui";

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

export function collectFolders(tree: KnowledgeTreeFolder): Array<{ path: string; label: string }> {
  const list: Array<{ path: string; label: string }> = [{ path: "", label: "资料库根目录" }];
  const visit = (folder: KnowledgeTreeFolder) => {
    for (const child of folder.children) {
      list.push({ path: child.path, label: child.path });
      visit(child);
    }
  };
  visit(tree);
  return list;
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
  const allFolders = collectFolders(tree);

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
            allFolders={allFolders}
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
            allFolders={allFolders}
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
  allFolders,
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
  allFolders: Array<{ path: string; label: string }>;
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
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <li role="treeitem" aria-expanded={open} aria-selected={selected}>
      <div className={`library-tree-row folder ${selected ? "selected" : ""} ${menuOpen ? "menu-open" : ""}`} style={{ paddingLeft: 6 + depth * 14 }}>
        <button
          className="library-tree-disclosure"
          type="button"
          aria-label={open ? `折叠 ${folder.name}` : `展开 ${folder.name}`}
          onClick={() => onToggle(folder.path)}
        >
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
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
            {open ? <FolderOpen size={16} /> : <Folder size={16} />}
            <span>{folder.name}</span>
          </button>
        )}
        <span
          className="library-tree-meta"
          title={`${folder.material_count} 份${pending > 0 ? ` · ${pending} 份未提取` : ""}`}
        >
          {folder.material_count} 份
          {pending > 0 && <em className="library-tree-pending"> · {pending} 份未提取</em>}
        </span>
        {onDeleteFolder && (
          <div className="library-tree-actions">
            <DesktopMenu
              compactTrigger
              ariaLabel={`${folder.name} 的更多操作`}
              triggerIcon={<MoreHorizontal size={16} />}
              align="right"
              onOpenChange={setMenuOpen}
              items={[{ id: "delete-folder", label: "删除文件夹", danger: true, onSelect: () => onDeleteFolder(folder.path) }]}
            />
          </div>
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
          {(folder.children.length > 0 || folder.files.length > 0) && (
            <ul role="group">
              {folder.children.map((child) => (
                <TreeFolder
                  key={child.path}
                  folder={child}
                  depth={depth + 1}
                  expanded={expanded}
                  allFolders={allFolders}
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
                  allFolders={allFolders}
                  onOpenDocument={onOpenDocument}
                  onMoveDocument={onMoveDocument}
                  onArchiveDocument={onArchiveDocument}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </li>
  );
}

function TreeFile({
  file,
  depth,
  active,
  allFolders,
  onOpenDocument,
  onMoveDocument,
  onArchiveDocument,
}: {
  file: KnowledgeTreeFile;
  depth: number;
  active: boolean;
  allFolders: Array<{ path: string; label: string }>;
  onOpenDocument: (documentId: string) => void;
} & TreeActions) {
  const tone = treeStatusTone(file);
  const [renaming, setRenaming] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const currentParent = file.path.includes("/") ? file.path.slice(0, file.path.lastIndexOf("/")) : "";
  const moveTargets = allFolders.filter((target) => target.path !== currentParent);
  const detail = [
    file.indexed ? `${file.chunk_count} 个片段` : "还没同步进索引",
    file.modified_at ? `更新于 ${new Date(file.modified_at).toLocaleDateString("zh-CN")}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  const menuItems: DesktopMenuItem[] = [];
  if (onMoveDocument && file.document_id) {
    menuItems.push({ id: "rename", label: "重命名", onSelect: () => setRenaming(true) });
    if (moveTargets.length > 0) {
      menuItems.push({
        id: "move",
        label: "移动到",
        children: moveTargets.map((target) => ({
          id: `move-${target.path || "root"}`,
          label: target.label,
          onSelect: () => onMoveDocument(file.document_id as string, target.path ? `${target.path}/${file.name}` : file.name),
        })),
      });
    }
  }
  if (onArchiveDocument && file.document_id) {
    menuItems.push({
      id: "archive",
      label: "归档",
      onSelect: () => onArchiveDocument(file.document_id as string, file.name),
    });
  }

  return (
    <li role="treeitem" aria-selected={active}>
      <div className={`library-tree-row file ${active ? "active" : ""} ${menuOpen ? "menu-open" : ""}`} style={{ paddingLeft: 6 + depth * 14 }}>
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
                onMoveDocument?.(documentId, currentParent ? `${currentParent}/${value}` : value);
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
            <FileText size={16} />
            <span className="library-tree-name">{file.name}</span>
            <span className={`library-tree-dot ${tone}`} title={TONE_LABEL[tone]} aria-label={TONE_LABEL[tone]} />
          </button>
        )}
        {menuItems.length > 0 && (
          <div className="library-tree-actions">
            <DesktopMenu
              compactTrigger
              ariaLabel={`${file.name} 的更多操作`}
              triggerIcon={<MoreHorizontal size={16} />}
              align="right"
              onOpenChange={setMenuOpen}
              items={menuItems}
            />
          </div>
        )}
      </div>
    </li>
  );
}
