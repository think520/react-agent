import { FormEvent, useState } from "react";
import { FolderOpen, Library, X } from "lucide-react";

import { ErrorNotice, IconButton } from "./common";

export function LibrarySetupDialog({
  onClose,
  onCreate,
  onOpen,
}: {
  onClose: () => void;
  onCreate: (name: string, parentPath: string) => Promise<void>;
  onOpen: (path: string) => Promise<void>;
}) {
  const [mode, setMode] = useState<"create" | "open">("create");
  const [name, setName] = useState("我的学习资料库");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!path.trim() || (mode === "create" && !name.trim())) return;
    setBusy(true);
    setError("");
    try {
      if (mode === "create") await onCreate(name.trim(), path.trim());
      else await onOpen(path.trim());
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
        <div><span>Local Library</span><h2 id="library-setup-title">{mode === "create" ? "创建本地资料库" : "打开已有资料库"}</h2></div>
        <IconButton label="关闭" onClick={onClose}><X size={18} /></IconButton>
      </header>
      <div className="library-mode-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "create"} className={mode === "create" ? "active" : ""} onClick={() => setMode("create")}>新建</button>
        <button type="button" role="tab" aria-selected={mode === "open"} className={mode === "open" ? "active" : ""} onClick={() => setMode("open")}>打开文件夹</button>
      </div>
      {mode === "create" && <label><span>资料库名称</span><input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} /></label>}
      <label><span>{mode === "create" ? "保存到这个目录" : "资料库文件夹路径"}</span><div className="path-input"><FolderOpen size={17} /><input value={path} placeholder="例如 D:\\Learning" onChange={(event) => setPath(event.target.value)} /></div></label>
      {error && <ErrorNotice message={error} />}
      <footer><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy || !path.trim()}>{busy ? "正在处理" : mode === "create" ? "创建资料库" : "打开资料库"}</button></footer>
    </form>
  </div>;
}
