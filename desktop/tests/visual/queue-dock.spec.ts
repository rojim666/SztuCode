import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"]) {
  for (const wallpaper of ["none", "mist"]) {
    test(`queued and normal composer share appearance and toolbar position: ${theme}/${wallpaper}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width: 760, height: 620 });
      await page.goto(`/tests/visual/fixtures/queue-dock.html?theme=${theme}&wallpaper=${wallpaper}`);
      const dock = page.locator(".queue-dock");
      const appearance = () => dock.evaluate(element => {
        const style = getComputedStyle(element);
        const editor = element.querySelector("textarea")!;
        const toolbar = element.querySelector(".composer-toolbar")!;
        const bounds = element.getBoundingClientRect();
        const editorBounds = editor.getBoundingClientRect();
        const toolbarBounds = toolbar.getBoundingClientRect();
        return { background: style.backgroundColor, border: style.border, radius: style.borderRadius, shadow: style.boxShadow, x: bounds.x, width: bounds.width, editorHeight: editorBounds.height, editorX: editorBounds.x, toolbarY: toolbarBounds.y, toolbarX: toolbarBounds.x };
      });
      await page.getByRole("button", { name: "2 条待处理" }).click();
      await page.getByRole("heading", { name: "输入卡片" }).click();
      const queued = await appearance();
      if (theme === "light" && wallpaper === "none") await page.screenshot({ path: testInfo.outputPath("composer-queued.png") });
      await page.getByRole("button", { name: "删除待处理任务" }).first().click();
      await page.getByRole("button", { name: "删除待处理任务" }).click();
      await page.getByRole("heading", { name: "输入卡片" }).click();
      await expect(page.locator(".queue-dock__queue")).toBeHidden();
      expect(await appearance()).toEqual(queued);
      if (theme === "light" && wallpaper === "none") await page.screenshot({ path: testInfo.outputPath("composer-normal.png") });
    });
  }
}

test("queue dock supports collapse, edit, remove, and steer without layout overlap", async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 620 });
  await page.goto("/tests/visual/fixtures/queue-dock.html", { waitUntil: "domcontentloaded" });

  const summary = page.getByRole("button", { name: "2 条待处理" });
  await expect(summary).toBeVisible();
  await summary.click();
  await expect(page.getByText("补充接口错误态测试", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "退回输入框编辑" }).first().click();
  const editor = page.getByRole("textbox", { name: "任务输入" });
  await editor.fill("补充队列回归测试");
  await page.getByRole("button", { name: "追加任务" }).click();
  await page.getByRole("button", { name: "2 条待处理" }).click();
  await expect(page.getByText("补充队列回归测试", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "删除待处理任务" }).first().click();
  await expect(page.getByText("整理本轮改动", { exact: false })).toBeHidden();
  await page.getByRole("button", { name: "转入当前轮" }).click();
  await expect(page.locator(".queue-dock__queue")).toBeHidden();

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
