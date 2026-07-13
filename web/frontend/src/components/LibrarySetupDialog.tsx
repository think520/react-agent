import { FormEvent, useState } from "react";
import { FolderOpen, Library, X } from "lucide-react";

import { ErrorNotice, IconButton } from "./common";
import type { LibraryMigrationPreview } from "../types";

export function LibrarySetupDialog({
  onClose,
  onCreate,
  onOpen,
  onPreviewMigration,
  onMigrate,
}: {
  onClose: () => void;
  onCreate: (name: string, parentPath: string) => Promise<void>;
  onOpen: (path: string) => Promise<void>;
  onPreviewMigration: (path: string) => Promise<LibraryMigrationPreview>;
  onMigrate: (name: string, path: string) => Promise<void>;
}) {
  const [mode, setMode] = useState<"create" | "open" | "migrate">("create");
  const [name, setName] = useState("我的学习资料库");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<LibraryMigrationPreview | null>(null);

  function selectMode(next: "create" | "open" | "migrate") {
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
      } else {
        await onMigrate(name.trim() || preview.folder_name, path.trim());
      }
      onClose();
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
        <div><span>Local Library</span><h2 id="library-setup-title">{mode === "create" ? "创建本地资料库" : mode === "open" ? "打开已有资料库" : "升级旧资料文件夹"}</h2></div>
        <IconButton label="关闭" onClick={onClose}><X size={18} /></IconButton>
      </header>
      <div className="library-mode-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "create"} className={mode === "create" ? "active" : ""} onClick={() => selectMode("create")}>新建</button>
        <button type="button" role="tab" aria-selected={mode === "open"} className={mode === "open" ? "active" : ""} onClick={() => selectMode("open")}>打开</button>
        <button type="button" role="tab" aria-selected={mode === "migrate"} className={mode === "migrate" ? "active" : ""} onClick={() => selectMode("migrate")}>升级旧文件夹</button>
      </div>
      {mode !== "open" && <label><span>资料库名称</span><input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>}
      <label><span>{mode === "create" ? "保存到这个目录" : mode === "open" ? "资料库文件夹路径" : "需要原地升级的旧文件夹"}</span><div className="path-input"><FolderOpen size={17} /><input value={path} placeholder="例如 D:\\Learning" onChange={(event) => { setPath(event.target.value); setPreview(null); }} /></div></label>
      {preview && <section className="library-migration-preview" aria-label="迁移扫描结果">
        <header><strong>{preview.already_initialized ? "这个文件夹已经初始化" : "可以原地升级"}</strong><span>{preview.folder_name}</span></header>
        <div><span><strong>{preview.material_count}</strong> 份可索引资料</span><span><strong>{(preview.size_bytes / 1024 / 1024).toFixed(1)} MB</strong> 文件夹体积</span><span><strong>{preview.wiki_pages}</strong> 个现有 Wiki 页面</span><span><strong>{preview.legacy_source_count}</strong> 个旧资料子目录</span></div>
        <p>确认后只会增加 Bobodan 描述文件和本地索引，不移动或删除原文件。</p>
      </section>}
      {error && <ErrorNotice message={error} />}
      <footer><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy || !path.trim()}>{busy ? (mode === "migrate" && preview ? "正在升级并同步" : "正在处理") : mode === "create" ? "创建资料库" : mode === "open" ? "打开资料库" : preview ? "确认原地升级" : "扫描文件夹"}</button></footer>
    </form>
  </div>;
}
