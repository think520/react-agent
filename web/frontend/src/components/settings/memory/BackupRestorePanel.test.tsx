import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../lib/api";
import { BackupRestorePanel } from "./BackupRestorePanel";

const mockApi = vi.hoisted(() => ({
  backupPlan: vi.fn(),
  createBackup: vi.fn(),
  backupDownloadUrl: vi.fn((id: string) => `/api/backup/download/${id}`),
  verifyBackupFile: vi.fn(),
  restoreBackupFile: vi.fn(),
  libraryDefaults: vi.fn(),
}));

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../../lib/api")>("../../../lib/api");
  return { ...actual, api: { ...actual.api, ...mockApi } };
});

const ACTIVE_LIBRARY = {
  library_id: "lib-1",
  name: "算法与数据结构",
  created_at: "2026-11-20T00:00:00+00:00",
  last_opened_at: "2026-11-20T00:00:00+00:00",
  active: true,
  available: true,
};

describe("BackupRestorePanel (W4-RESTORE-01)", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.backupPlan.mockResolvedValue({
      library: { library_id: "lib-1", name: "算法与数据结构", is_portable: true },
      library_databases: ["knowledge.db", "bobodan.db"],
      includes_global: true,
      global_items: ["personal-knowledge.db", "preferences.json"],
      excluded_items: [{ name: "provider.json", reason: "云端 API 密钥与供应商凭证默认不导出" }],
      counts: { materials: 3, questions: 8, notes_and_knowledge: 2, sessions: 4 },
    });
    mockApi.libraryDefaults.mockResolvedValue({
      name: "Bobodan 资料库",
      parent_path: "D:\\Restored",
      root_path: "D:\\Restored\\Bobodan 资料库",
    });
  });

  it("discloses global scope and explicit API key exclusion, and creates a downloadable backup", async () => {
    mockApi.createBackup.mockResolvedValue({
      backup_id: "bobodan-backup-test.zip",
      filename: "bobodan-backup-test.zip",
      size_bytes: 2048,
      created_at: "2026-11-20T06:00:00+00:00",
      library: { library_id: "lib-1", name: "算法与数据结构", is_portable: true },
      includes_global: true,
      counts: { materials: 3, questions: 8, notes_and_knowledge: 2, sessions: 4 },
    });

    render(<BackupRestorePanel activeLibrary={ACTIVE_LIBRARY} />);

    await waitFor(() => {
      expect(screen.getByText(/跨库个人知识、学习与界面偏好/)).toBeTruthy();
    });
    expect(screen.getByText(/provider\.json/)).toBeTruthy();
    expect(screen.getByText(/3 份资料 · 8 道题/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "创建整库备份" }));

    await waitFor(() => {
      expect(mockApi.createBackup).toHaveBeenCalledWith(true);
      expect(screen.getByRole("link", { name: "下载 ZIP" }).getAttribute("href")).toBe(
        "/api/backup/download/bobodan-backup-test.zip",
      );
    });
  });

  it("verifies uploaded archive and shows rollback error hint when restore fails", async () => {
    mockApi.verifyBackupFile.mockResolvedValue({
      valid: true,
      created_at: "2026-11-20T06:00:00+00:00",
      library: { library_id: "lib-1", name: "算法与数据结构", is_portable: true },
      storage_dir: ".bobodan",
      includes_global: true,
      global_items: ["preferences.json"],
      excluded_items: [],
      counts: { materials: 3, questions: 8, sessions: 4 },
      sqlite_databases: ["library/.bobodan/knowledge.db"],
      verified_files: 10,
    });
    mockApi.restoreBackupFile.mockRejectedValue(
      new ApiError("恢复失败", "restore_failed", 500, { rolled_back: true }),
    );

    render(<BackupRestorePanel activeLibrary={ACTIVE_LIBRARY} />);

    const input = screen.getByLabelText("选择备份压缩包") as HTMLInputElement;
    const file = new File(["zip"], "backup.zip", { type: "application/zip" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/校验通过：共 10 个文件/)).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "恢复到目标目录" }));
    const confirmButton = await screen.findByRole("button", { name: "开始恢复" });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mockApi.restoreBackupFile).toHaveBeenCalledWith(file, {
        targetDir: "D:\\Restored\\Bobodan 资料库",
        restoreGlobal: true,
        activate: true,
      });
      expect(screen.getByRole("alert").textContent).toContain("已自动回滚到恢复前状态");
    });
  });
});
