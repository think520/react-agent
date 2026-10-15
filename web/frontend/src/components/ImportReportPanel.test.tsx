import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ImportReportPanel } from "./ImportReportPanel";

/**
 * E8：导入结果要**逐文件**说清楚（文件名 + 可行动原因 + 重试）。
 * 核对结论：之前整批只有一句"N 份解析失败"，用户既不知道是哪几份、也不能重试。
 */

afterEach(cleanup);

const results = [
  { filename: "good.md", status: "imported", searchable: true },
  { filename: "broken.pdf", status: "imported", searchable: false, extraction: "error" },
  { filename: "notes.exe", status: "rejected", reason: "unsupported_file_type" },
];

it("逐条列出文件名与原因，需要处理的那几份排在最前", () => {
  render(<ImportReportPanel results={results} canRetry onRetryFailed={() => {}} onDismiss={() => {}} />);

  expect(screen.getByText("broken.pdf")).toBeTruthy();
  expect(screen.getByText("解析失败：没能从这份文件里提取出文本")).toBeTruthy();
  expect(screen.getByText("notes.exe")).toBeTruthy();
  expect(screen.getByText("格式不支持（可用 .md / .txt / .pdf / .docx / .pptx）")).toBeTruthy();
  expect(screen.getByText("good.md")).toBeTruthy();

  const rows = screen.getAllByTestId("import-report-row");
  expect(rows[0].textContent).toContain("broken.pdf");
  expect(rows.at(-1)!.textContent).toContain("good.md");
});

it("有可重试的文件时给出重试按钮，点了就回调", () => {
  const onRetryFailed = vi.fn();
  render(<ImportReportPanel results={results} canRetry onRetryFailed={onRetryFailed} onDismiss={() => {}} />);

  fireEvent.click(screen.getByRole("button", { name: /重试/ }));
  expect(onRetryFailed).toHaveBeenCalledTimes(1);
});

it("没有需要处理的文件时不摆重试按钮（别给假按钮）", () => {
  render(
    <ImportReportPanel
      results={[{ filename: "good.md", status: "imported", searchable: true }]}
      canRetry
      onRetryFailed={() => {}}
      onDismiss={() => {}}
    />,
  );
  expect(screen.queryByRole("button", { name: /重试/ })).toBeNull();
});

it("全部没有可重试的文件对象时不显示重试按钮", () => {
  render(<ImportReportPanel results={results} canRetry={false} onRetryFailed={() => {}} onDismiss={() => {}} />);
  expect(screen.queryByRole("button", { name: /重试/ })).toBeNull();
});
