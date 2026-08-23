import { expect, test } from "@playwright/test";

test("queue dock supports collapse, edit, remove, and steer without layout overlap", async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 620 });
  await page.goto("/tests/visual/fixtures/queue-dock.html", { waitUntil: "domcontentloaded" });

  const summary = page.getByRole("button", { name: "2 条待处理" });
  await expect(summary).toBeVisible();
  await summary.click();
  await expect(page.getByText("补充接口错误态测试", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "编辑待处理任务" }).first().click();
  const editor = page.getByRole("textbox", { name: "编辑待处理任务" });
  await editor.fill("补充队列回归测试");
  await page.getByRole("button", { name: "保存编辑" }).click();
  await expect(page.getByText("补充队列回归测试", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "删除待处理任务" }).last().click();
  await expect(page.getByText("整理本轮改动", { exact: false })).toBeHidden();
  await page.getByRole("button", { name: "转入当前轮" }).click();
  await expect(page.locator(".queue-dock")).toBeHidden();

  const composer = page.locator(".kimi-composer");
  await expect(composer).toBeVisible();
  const bounds = await composer.boundingBox();
  expect(bounds?.width).toBeLessThanOrEqual(712);
});

test("queue dock keeps controls inside a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 620 });
  await page.goto("/tests/visual/fixtures/queue-dock.html", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "2 条待处理" }).click();

  const overflow = await page.locator(".queue-dock").evaluate((element) => ({
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
  await expect(page.getByRole("button", { name: "转入当前轮" }).first()).toBeVisible();
});
