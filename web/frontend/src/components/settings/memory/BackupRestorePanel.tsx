import { useEffect, useRef, useState } from "react";
import { Archive, CheckCircle2, Download, RotateCcw, Upload } from "lucide-react";

import { api } from "../../../lib/api";
import { userMessageFor } from "../../../lib/errorHints";
import type { BackupPlan, BackupSummary, BackupVerification, LibrarySummary } from "../../../types";
import { useConfirm } from "../../../ui/Modal";
import { SettingsRow, SettingsSection, SettingsToggle } from "../SettingsPrimitives";

const GLOBAL_ITEM_LABELS: Record<string, string> = {
  "personal-knowledge.db": "跨库个人知识",
  "usage.db": "AI 用量记录",
  "preferences.json": "学习与界面偏好",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatBackupTime(iso: string): string {
  if (!iso) return "";
  return iso.replace("T", " ").replace(/\+00:00|Z$/, " UTC").slice(0, 19);
}

type RestoreSource = { kind: "file"; file: File; label: string } | { kind: "saved"; backupId: string; label: string };

export function BackupRestorePanel({ activeLibrary }: { activeLibrary: LibrarySummary | null }) {
  const { confirm, confirmElement } = useConfirm();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [includeGlobal, setIncludeGlobal] = useState(true);
  const [plan, setPlan] = useState<BackupPlan | null>(null);
  const [backups, setBackups] = useState<BackupSummary[]>([]);
  const [creating, setCreating] = useState(false);
  const [latestBackup, setLatestBackup] = useState<BackupSummary | null>(null);

  const [restoreSource, setRestoreSource] = useState<RestoreSource | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verification, setVerification] = useState<BackupVerification | null>(null);
  const [targetDir, setTargetDir] = useState("");
  const [restoreGlobal, setRestoreGlobal] = useState(false);
  const [restoring, setRestoring] = useState(false);

  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void api.backupList().then((result) => {
      if (!cancelled) setBackups(result.backups || []);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!activeLibrary) {
      setPlan(null);
      return;
    }
    let cancelled = false;
    void api.backupPlan(includeGlobal).then((next) => {
      if (!cancelled) setPlan(next);
    }).catch((reason) => {
      if (!cancelled) setError(userMessageFor(reason, "暂时无法读取备份清单。"));
    });
    return () => { cancelled = true; };
  }, [activeLibrary, includeGlobal]);

  async function ensureDefaultTargetDir() {
    if (targetDir) return;
    try {
      const defaults = await api.libraryDefaults();
      setTargetDir(defaults.root_path);
    } catch {
      // Optional helper; user can still enter target directory manually.
    }
  }

  async function handleCreateBackup() {
    if (!activeLibrary || creating) return;
    setCreating(true);
    setError("");
    setNotice("");
    try {
      const created = await api.createBackup(includeGlobal);
      setLatestBackup(created);
      setBackups((current) => [created, ...current.filter((item) => item.backup_id !== created.backup_id)]);
      setNotice(`已生成备份 ${created.filename}（${formatBytes(created.size_bytes)}），已通过 SQLite 完整性校验。`);
    } catch (reason) {
      setError(userMessageFor(reason, "创建备份失败。"));
    } finally {
      setCreating(false);
    }
  }

  async function verifySource(source: RestoreSource) {
    setRestoreSource(source);
    setVerification(null);
    setRestoreGlobal(false);
    setError("");
    setNotice("");
    setVerifying(true);
    try {
      const result = source.kind === "file"
        ? await api.verifyBackupFile(source.file)
        : await api.verifySavedBackup(source.backupId);
      setVerification(result);
      setRestoreGlobal(result.includes_global);
      await ensureDefaultTargetDir();
      setNotice(`校验通过：共 ${result.verified_files} 个文件、${result.sqlite_databases.length} 个 SQLite 数据库完整无损。`);
    } catch (reason) {
      setError(userMessageFor(reason, "备份包校验失败。"));
    } finally {
      setVerifying(false);
    }
  }

  async function handleFileSelect(file: File | null) {
    if (!file) {
      setRestoreSource(null);
      setVerification(null);
      return;
    }
    await verifySource({ kind: "file", file, label: `${file.name}（${formatBytes(file.size)}）` });
  }

  async function handleRestore() {
    if (!restoreSource || !verification || restoring) return;
    const cleanedTarget = targetDir.trim();
    if (!cleanedTarget) {
      setError("请填写一个空白的目标文件夹路径用于恢复。");
      return;
    }
    const ok = await confirm({
      title: "确认从备份恢复资料库",
      detail: restoreGlobal && verification.includes_global
        ? "将把备份中的资料库恢复到所选空白目录，并同时恢复全局偏好与跨库个人知识。不会导入或覆盖云端 API 密钥；若中途失败将自动回滚。"
        : "将把备份中的资料库恢复到所选空白目录并注册到本机。不会修改现有全局设置或 API 密钥；若中途失败将自动回滚。",
      confirmLabel: "开始恢复",
    });
    if (!ok) return;

    setRestoring(true);
    setError("");
    setNotice("");
    try {
      const options = {
        targetDir: cleanedTarget,
        restoreGlobal: restoreGlobal && verification.includes_global,
        activate: true,
      };
      const result = restoreSource.kind === "file"
        ? await api.restoreBackupFile(restoreSource.file, options)
        : await api.restoreSavedBackup(restoreSource.backupId, options);
      setNotice(`已恢复资料库「${result.library.name}」并完成校验（${result.verified_files} 个文件）。刷新页面或切换资料库即可使用。`);
    } catch (reason) {
      setError(userMessageFor(reason, "恢复失败，已尝试回滚到恢复前状态。"));
    } finally {
      setRestoring(false);
    }
  }

  const globalSummary = plan?.global_items.length
    ? plan.global_items.map((name) => GLOBAL_ITEM_LABELS[name] || name).join("、")
    : "当前无可导出的全局文件";
  const recentBackups = backups.slice(0, 5);

  return <>
    {confirmElement}
    <SettingsSection
      title="整库备份与恢复"
      description="按 SQLite 在线快照与 SHA-256 清单打包资料库原件、检索索引、题库与掌握度、对话、笔记与知识地图，支持校验与异地干净目录恢复。"
    >
      <SettingsRow
        label="备份包含全局数据"
        hint={includeGlobal ? `将同时打包：${globalSummary}` : "仅打包当前资料库，不包含全局偏好与跨库个人知识"}
      >
        <SettingsToggle label="备份包含全局数据" checked={includeGlobal} onChange={setIncludeGlobal} />
      </SettingsRow>

      <SettingsRow
        label="创建整库备份"
        hint={
          plan
            ? `${plan.counts.materials ?? 0} 份资料 · ${plan.counts.questions ?? 0} 道题 · ${plan.counts.notes_and_knowledge ?? 0} 条笔记 · ${plan.counts.sessions ?? 0} 个会话`
            : activeLibrary ? "正在读取资料库摘要…" : "请先选择资料库"
        }
      >
        <button className="quiet-button" type="button" disabled={!activeLibrary || creating} onClick={() => void handleCreateBackup()}>
          <Archive size={15} />
          {creating ? "正在打包校验…" : "创建整库备份"}
        </button>
      </SettingsRow>

      {latestBackup && (
        <SettingsRow label="最新备份" hint={`${latestBackup.filename} · ${formatBytes(latestBackup.size_bytes)}`}>
          <a className="quiet-button" href={api.backupDownloadUrl(latestBackup.backup_id)} download={latestBackup.filename}>
            <Download size={15} />下载 ZIP
          </a>
        </SettingsRow>
      )}

      {recentBackups.length > 0 && (
        <details className="migration-preview">
          <summary>本机已保存的备份（最近 {recentBackups.length} 份）</summary>
          <div>
            {recentBackups.map((item) => (
              <div className="setting-row" key={item.backup_id}>
                <span>
                  <strong>{item.library?.name || item.filename}</strong>
                  <small>{formatBytes(item.size_bytes)}{item.created_at ? ` · ${formatBackupTime(item.created_at)}` : ""}{item.includes_global ? " · 含全局数据" : ""}</small>
                </span>
                <div className="migration-actions">
                  <a className="quiet-button" href={api.backupDownloadUrl(item.backup_id)} download={item.filename}>
                    <Download size={14} />下载
                  </a>
                  <button
                    className="quiet-button"
                    type="button"
                    disabled={verifying || restoring}
                    onClick={() => void verifySource({ kind: "saved", backupId: item.backup_id, label: item.filename })}
                  >
                    <RotateCcw size={14} />校验恢复
                  </button>
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      <p className="settings-model-hint">
        安全边界：备份默认<strong>不包含</strong> <code>provider.json</code>（云端 API 密钥）、本地 <code>.env</code> 与本机 <code>libraries.json</code> 路径表；换机恢复后请重新填写模型密钥。
      </p>

      <SettingsRow
        label="校验并恢复备份包"
        hint={restoreSource ? restoreSource.label : "选择 .zip 备份包，先校验 SHA-256 与数据库完整性，再恢复到空白目录"}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip,application/zip"
          hidden
          aria-label="选择备份压缩包"
          onChange={(event) => void handleFileSelect(event.target.files?.[0] || null)}
        />
        <button className="quiet-button" type="button" disabled={verifying || restoring} onClick={() => fileInputRef.current?.click()}>
          <Upload size={15} />
          {verifying ? "正在校验…" : "选择备份包"}
        </button>
      </SettingsRow>

      {verification && (
        <>
          <p className="settings-model-hint">
            <CheckCircle2 size={14} style={{ display: "inline", verticalAlign: "-2px", marginRight: 5 }} />
            备份资料库：<strong>{verification.library.name || "未命名资料库"}</strong> · {verification.counts.materials ?? 0} 份资料 · {verification.counts.questions ?? 0} 道题 · {verification.counts.sessions ?? 0} 个会话
          </p>
          <label className="settings-field">
            <span>恢复目标空白目录</span>
            <input
              type="text"
              value={targetDir}
              placeholder="例如：D:\Bobodan\RestoredLibrary"
              onChange={(event) => setTargetDir(event.target.value)}
            />
          </label>
          {verification.includes_global && (
            <label className="migration-check">
              <input
                type="checkbox"
                checked={restoreGlobal}
                onChange={(event) => setRestoreGlobal(event.target.checked)}
              />
              <span>同时恢复全局数据（{verification.global_items.map((name) => GLOBAL_ITEM_LABELS[name] || name).join("、")}；不含 API 密钥）</span>
            </label>
          )}
          <div className="migration-actions">
            <button className="primary-button" type="button" disabled={restoring || !targetDir.trim()} onClick={() => void handleRestore()}>
              <RotateCcw size={15} />
              {restoring ? "正在恢复并核对…" : "恢复到目标目录"}
            </button>
          </div>
        </>
      )}

      {notice && <p className="settings-model-hint" role="status">{notice}</p>}
      {error && <p className="settings-warning" role="alert">{error}</p>}
    </SettingsSection>
  </>;
}
