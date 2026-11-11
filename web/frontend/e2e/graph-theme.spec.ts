import { expect, test } from "@playwright/test";

import { json, mockApi } from "./fixtures/mockApi";

/**
 * 知识地图画布随主题取色（2026-11-11）。Sigma 画在 canvas 上，DOM 断言够不着；
 * 这里读画布像素：暗色主题下标签贴片必须是深色，而不是改造前写死的米白。
 */
const concepts = [
  { concept_id: "c1", name: "Dijkstra 算法", level: "cluster", definition: "", aliases: [], topic_ids: [], note: "", created_at: 0, updated_at: 0, x: 0, y: 0 },
  { concept_id: "c2", name: "贪心策略", level: "core", definition: "", aliases: [], topic_ids: [], note: "", created_at: 0, updated_at: 0, x: 3, y: 1 },
  { concept_id: "c3", name: "负权边", level: "detail", definition: "", aliases: [], topic_ids: [], note: "", created_at: 0, updated_at: 0, x: -3, y: 1 },
];
const relationships = [
  { relationship_id: "r1", from_id: "c1", to_id: "c2", rel_type: "uses", evidence_level: "user", note: "" },
  { relationship_id: "r2", from_id: "c1", to_id: "c3", rel_type: "limits", evidence_level: "model", note: "" },
];

test("the knowledge map canvas follows the dark theme", async ({ page }) => {
  await mockApi(page, { appearance: { theme: "dark" } });
  await page.route("**/api/graph/state**", (route) => route.fulfill(json({ concepts, relationships, candidates: [], pending_count: 0, total_concepts: 3 })));
  await page.route("**/api/graph/topics**", (route) => route.fulfill(json({ topics: [] })));
  await page.route("**/api/graph/views**", (route) => route.fulfill(json({ views: [] })));

  await page.goto("/knowledge-map");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const surface = page.locator(".graph-canvas").first();
  await expect(surface.locator("canvas").first()).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(1200);
  const shot = await surface.screenshot({ path: process.env.GRAPH_SHOT || "test-results/graph-dark.png" });

  // 读的是**用户看到的合成结果**（截图），不是某一层 canvas：改造前标签是米白贴片。
  const brightPixels = await page.evaluate(async (base64: string) => {
    const image = new Image();
    image.src = "data:image/png;base64," + base64;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    let bright = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] > 225 && data[i + 1] > 225 && data[i + 2] > 215) bright += 1;
    }
    return bright;
  }, shot.toString("base64"));
  // 改造前两个标签贴片约 1000+ 个近白像素；改造后只剩文字笔画本身的少量浅色像素。
  expect(brightPixels).toBeLessThan(300);
});
