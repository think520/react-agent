import { FormEvent, useEffect, useState } from "react";
import { FolderOpen, Library, X } from "lucide-react";

import { api } from "../lib/api";
import { errorCodeOf } from "../lib/errorHints";
import { ErrorNotice, IconButton } from "./common";
import type { LibraryMigrationPreview } from "../types";
import { Modal } from "../ui/Modal";

export type LibrarySetupMode = "create" | "open" | "migrate";

/** 用户没改过名字时才用后端的默认名覆盖（改了就以用户的为准）。 */
const DEFAULT_NAME = "我的学习资料库";

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
  const [name, setName] = useState(DEFAULT_NAME);
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // W1 E1：错误码要一起留着 —— 界面才能说出"下一步"（换名称 / 重新接入 / 稍后重试）。
  const [errorCode, setErrorCode] = useState("");
  const [preview, setPreview] = useState<LibraryMigrationPreview | null>(null);

  const [rootPreview, setRootPreview] = useState("");

  // W1 E2：默认值只从后端来（以前这里硬编码 «~/Documents/Bobodan»，与后端的默认目录不是一处）。
  useEffect(() => {
    if (mode !== "create" || path.trim()) return;
    let alive = true;
    void api.libraryDefaults()
      .then((defaults) => {
        if (!alive) return;
        setPath((current) => current.trim() || defaults.parent_path);
        setName((current) => (current === DEFAULT_NAME ? defaults.name : current));
      })
      .catch(() => { /* 拿不到默认值就让用户自己填，不编一个可能不对的路径 */ });
    return () => { alive = false; };
  }, [mode, path]);

  // 「保存到这个目录」填的是**父目录**，而真正创建的是「父目录 + 名称」。
  // 把最终位置显示出来（规则由后端算，和创建共用一套），避免所见非所得。
  useEffect(() => {
    if (mode !== "create") {
      setRootPreview("");
      return;
    }
    const trimmedName = name.trim();
    const trimmedParent = path.trim();
    if (!trimmedName || !trimmedParent) {
      setRootPreview("");
      return;
    }
    const timer = window.setTimeout(() => {
      void api.libraryRootPreview(trimmedName, trimmedParent)
        .then((result) => setRootPreview(result.root_path))
        .catch(() => setRootPreview(""));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [mode, name, path]);

  function selectMode(next: LibrarySetupMode) {
    setMode(next);
    setPreview(null);
    setError("");
    setErrorCode("");
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
      setErrorCode(errorCodeOf(reason));
    } finally {
      setBusy(false);
    }
  }

  return <Modal backdropClassName="dialog-layer" onClose={onClose} labelledBy="library-setup-title" className="library-setup-dialog">
    <form onSubmit={submit}>
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
      <label><span>{mode === "create" ? "保存到这个目录" : mode === "open" ? "Bobodan 资料库路径" : "需要原地接入的资料文件夹"}</span><div className="path-input"><FolderOpen size={17} /><input value={path} placeholder="例如 D:\\Learning" onChange={(event) => { setPath(event.target.value); setPreview(null); }} /></div>{mode === "create" && <p className="library-path-hint">Bobodan 会把你的资料和本地索引保存在这个文件夹，建议放在文档目录；文件夹不存在时会自动创建。</p>}</label>
      {mode === "create" && rootPreview && (
        <p className="library-root-preview">将创建：<code>{rootPreview}</code></p>
      )}
      {preview && <section className="library-migration-preview" aria-label="接入扫描结果">
        <header><strong>{preview.already_initialized ? "这是一个 Bobodan 资料库" : "可以原地接入"}</strong><span>{preview.folder_name}</span></header>
        <div><span><strong>{preview.material_count}</strong> 份可索引资料</span><span><strong>{(preview.size_bytes / 1024 / 1024).toFixed(1)} MB</strong> 文件夹体积</span><span><strong>{preview.wiki_pages}</strong> 个现有 Wiki 页面</span><span><strong>{preview.legacy_source_count}</strong> 个旧资料子目录</span></div>
        <p>确认后只会增加 Bobodan 描述文件和本地索引，不移动或删除原文件。</p>
      </section>}
      {error && <ErrorNotice message={error} code={errorCode} />}
      <footer><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy || !path.trim()}>{busy ? (mode === "migrate" && preview ? (preview.already_initialized ? "正在打开资料库" : "正在接入并同步") : "正在处理") : mode === "create" ? (importCount ? "创建并继续导入" : "新建资料库") : mode === "open" ? (importCount ? "打开并继续导入" : "打开资料库") : preview ? (preview.already_initialized ? (importCount ? "打开并继续导入" : "打开这个资料库") : importCount ? "接入并继续导入" : "确认原地接入") : "扫描文件夹"}</button></footer>
    </form>
  </Modal>;
}
