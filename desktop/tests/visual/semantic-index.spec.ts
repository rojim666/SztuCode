import { expect, test } from "@playwright/test";

test("索引面板显示构建进度、就绪统计并允许清除", async ({ page }) => {
  await page.goto("/tests/visual/fixtures/semantic-index.html");
  await page.getByRole("button", { name: "语义索引尚未建立" }).click();
  const panel = page.getByRole("region", { name: "语义索引管理" });
  await panel.getByRole("button", { name: "重建索引" }).click();
  await expect(panel.getByRole("progressbar")).toBeVisible();
  await expect(panel.getByRole("button", { name: "清除索引" })).toBeDisabled();
  await expect(panel).toContainText("3 个文件 · 8 个片段");
  await page.screenshot({ path: "test-results/issue-145-index-ready.png" });
  await panel.getByRole("button", { name: "清除索引" }).click();
  await expect(panel).toContainText("语义索引尚未建立");
});

test("模型失败会显示原因和重建入口", async ({ page }) => {
  await page.goto("/tests/visual/fixtures/semantic-index.html?failed=1");
  await page.getByRole("button", { name: "语义索引失败" }).click();
  await expect(page.getByRole("alert")).toHaveText("本地模型加载失败");
  await expect(page.getByRole("button", { name: "重建索引" })).toBeEnabled();
});
