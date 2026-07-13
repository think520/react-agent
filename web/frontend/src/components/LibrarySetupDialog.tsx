import { FormEvent, useState } from "react";
import { FolderOpen, Library, X } from "lucide-react";

import { ErrorNotice, IconButton } from "./common";
import type { LibraryMigrationPreview } from "../types";

export type LibrarySetupMode = "create" | "open" | "migrate";

export function LibrarySetupDialog({
  onClose,
  onComplete,
  onCreate,
  onOpen,
  onPreviewMigration,
  onMigrate,
  initialMode = "create",
  importCount = 0,
}: {
  onClose: () => void;
  onComplete: () => void;
  onCreate: (name: string, parentPath: string) => Promise<void>;
  onOpen: (path: string) => Promise<void>;
  onPreviewMigration: (path: string) => Promise<LibraryMigrationPreview>;
  onMigrate: (name: string, path: string) => Promise<void>;
  initialMode?: LibrarySetupMode;
  importCount?: number;
}) {
  const [mode, setMode] = useState<LibrarySetupMode>(initialMode);
  const [name, setName] = useState("我的学习资料库");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<LibraryMigrationPreview | null>(null);

  function selectMode(next: LibrarySetupMode) {
    setMode(next);
    setPreview(null);
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!path.trim() || (mode === "create" && !name.trim())) return;
    setBusy(true);
    setError("");
    try {
      if (mode === "create") await onCreate(name.trim(), path.trim());
      else if (mode === "open") await onOpen(path.trim());
      else if (!preview) {
        const result = await onPreviewMigration(path.trim());
        setPreview(result);
        if (name === "我的学习资料库") setName(result.folder_name);
        return;
      } else if (preview.already_initialized) {
        await onOpen(path.trim());
      } else {
        await onMigrate(name.trim() || preview.folder_name, path.trim());
      }
      onComplete();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "资料库操作失败。");
    } finally {
      setBusy(false);
    }
  }

  return <div className="dialog-layer" role="presentation">
    <form className="library-setup-dialog" role="dialog" aria-modal="true" aria-labelledby="library-setup-title" onSubmit={submit}>
      <header>
        <span className="dialog-symbol"><Library size={20} /></span>
        <div><span>本地资料库</span><h2 id="library-setup-title">{importCount ? `准备导入 ${importCount} 份资料` : mode === "create" ? "新建空资料库" : mode === "open" ? "打开 Bobodan 资料库" : "接入现有资料文件夹"}</h2></div>
        <IconButton label="关闭" type="button" onClick={onClose}><X size={18} /></IconButton>
      </header>
      {importCount > 0 && <p className="library-setup-intro">先确定这些资料保存到哪个资料库。完成后 Bobodan 会继续导入并建立本地索引。</p>}
      <div className="library-mode-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "create"} className={mode === "create" ? "active" : ""} onClick={() => selectMode("create")}>新建</button>
        <button type="button" role="tab" aria-selected={mode === "open"} className={mode === "open" ? "active" : ""} onClick={() => selectMode("open")}>打开</button>
        <button type="button" role="tab" aria-selected={mode === "migrate"} className={mode === "migrate" ? "active" : ""} onClick={() => selectMode("migrate")}>接入旧文件夹</button>
      </div>
      {mode !== "open" && <label><span>资料库名称</span><input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>}
      <label><span>{mode === "create" ? "保存到这个目录" : mode === "open" ? "Bobodan 资料库路径" : "需要原地接入的资料文件夹"}</span><div className="path-input"><FolderOpen size={17} /><input value={path} placeholder="例如 D:\\Learning" onChange={(event) => { setPath(event.target.value); setPreview(null); }} /></div></label>
      {preview && <section className="library-migration-preview" aria-label="接入扫描结果">
        <header><strong>{preview.already_initialized ? "这是一个 Bobodan 资料库" : "可以原地接入"}</strong><span>{preview.folder_name}</span></header>
        <div><span><strong>{preview.material_count}</strong> 份可索引资料</span><span><strong>{(preview.size_bytes / 1024 / 1024).toFixed(1)} MB</strong> 文件夹体积</span><span><strong>{preview.wiki_pages}</strong> 个现有 Wiki 页面</span><span><strong>{preview.legacy_source_count}</strong> 个旧资料子目录</span></div>
        <p>确认后只会增加 Bobodan 描述文件和本地索引，不移动或删除原文件。</p>
      </section>}
      {error && <ErrorNotice message={error} />}
      <footer><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy || !path.trim()}>{busy ? (mode === "migrate" && preview ? (preview.already_initialized ? "正在打开资料库" : "正在接入并同步") : "正在处理") : mode === "create" ? (importCount ? "创建并继续导入" : "新建资料库") : mode === "open" ? (importCount ? "打开并继续导入" : "打开资料库") : preview ? (preview.already_initialized ? (importCount ? "打开并继续导入" : "打开这个资料库") : importCount ? "接入并继续导入" : "确认原地接入") : "扫描文件夹"}</button></footer>
    </form>
  </div>;
}
