import { expect, test } from "@playwright/test";

import { mockApi } from "./fixtures/mockApi";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

// L2-5（计算样式契约）：设置对话框的高度上限与底部主操作，必须在低高度视口里真的可见。
// 1280x600 是 Windows 桌面端常见的最小可用窗口，旧的 min-height: 620px 会在这里把
// 「保存助手设置」挤出视口，只能靠内容区滚动去够。
test("设置对话框在 1280x600 下不越界，助手设置的保存按钮可见", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "移动端是全屏 sheet，桌面窗口约束在这里不适用");
  await page.setViewportSize({ width: 1280, height: 600 });
  await page.goto("/chat?settings=assistant");

  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();

  const dialogBox = await dialog.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect(dialogBox!.y).toBeGreaterThanOrEqual(-1);
  expect(dialogBox!.y + dialogBox!.height).toBeLessThanOrEqual(601);

  const save = dialog.getByRole("button", { name: "保存助手设置" });
  await expect(save).toBeVisible();
  const saveBox = await save.boundingBox();
  expect(saveBox).not.toBeNull();
  expect(saveBox!.y + saveBox!.height).toBeLessThanOrEqual(601);

  // 主操作固定在对话框底部，不随内容区滚动而离开视口。
  const footerSticks = await dialog.locator(".settings-main").evaluate((main) => {
    const footer = document.querySelector(".settings-dialog-footer");
    if (!footer) return false;
    const dialogEl = document.querySelector(".settings-dialog");
    if (!dialogEl) return false;
    return dialogEl.contains(footer) && main.scrollHeight >= main.clientHeight;
  });
  expect(footerSticks).toBe(true);
});

test("助手设置的主操作在 1440x960 也固定在对话框底部", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "移动端是全屏 sheet，桌面窗口约束在这里不适用");
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto("/chat?settings=assistant");

  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();
  const dialogBox = await dialog.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect(dialogBox!.height).toBeLessThanOrEqual(840.5);

  const footer = dialog.locator(".settings-dialog-footer");
  await expect(footer).toBeVisible();
  const dialogBottom = dialogBox!.y + dialogBox!.height;
  const footerBox = await footer.boundingBox();
  expect(footerBox).not.toBeNull();
  expect(dialogBottom - (footerBox!.y + footerBox!.height)).toBeLessThanOrEqual(1.5);
});
