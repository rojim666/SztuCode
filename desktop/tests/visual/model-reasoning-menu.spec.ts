import { expect, test, type Page } from "@playwright/test";

type Fixture = {
  settingsCalls: Record<string, unknown>[];
  setSettingsError: (value: boolean) => void;
  setSettingsDelay: (value: number) => void;
};

test("八个模型时菜单保持紧凑，方向键浏览不改变模型", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 380, height: 700 });
  await page.goto("/tests/visual/fixtures/model-manager.html?menu&many");
  await page.getByRole("button", { name: "当前模型", exact: true }).click();
  const current = page.getByRole("menuitemradio", { name: "当前模型" });
  await expect(current).toBeEnabled();
  await current.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitemradio", { name: "内置模型" })).toBeFocused();
  await page.keyboard.press("End");
  await expect(page.getByRole("menuitemradio", { name: "openai-fast" })).toBeFocused();
  await expect(current).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Home");
  await expect(current).toBeFocused();
  const slider = page.getByRole("slider", { name: "思考强度" });
  await slider.press("ArrowRight");
  await expect(slider).toBeEnabled();
  await slider.press("ArrowRight");
  await expect(slider).toBeEnabled();
  const dialog = page.getByRole("dialog", { name: "选择模型" });
  const bounds = await dialog.boundingBox();
  expect(bounds!.height).toBeLessThanOrEqual(460);
  await expect(page.getByRole("button", { name: "添加和管理模型" })).toBeInViewport();
  await dialog.locator("header").click();
  await page.screenshot({ path: testInfo.outputPath("model-menu-balanced.png") });
});

async function openMenu(page: Page) {
  await page.goto("/tests/visual/fixtures/model-manager.html?menu", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "当前模型", exact: true }).click();
  const slider = page.getByRole("slider", { name: "思考强度" });
  await expect(slider).toBeEnabled();
  return slider;
}

test("快捷思考滑块支持键盘、模型切换和内置模型", async ({ page }, testInfo) => {
  const slider = await openMenu(page);
  await slider.press("End");
  await expect(page.getByRole("status", { name: "思考强度保存状态" })).toHaveText("已应用");
  await expect(slider).toBeFocused();
  await expect(slider).toHaveAttribute("aria-valuetext", "最高 · 最大思考投入");
  await page.getByRole("dialog", { name: "选择模型" }).locator("header").click();
  await page.screenshot({ path: testInfo.outputPath("reasoning-max-effects.png"), animations: "disabled" });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(() => page.locator(".reasoning-slider").evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === "running").length)).toBe(0);
  await page.keyboard.press("Escape");
  const trigger = page.getByRole("button", { name: "当前模型", exact: true });
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(slider).toHaveValue("5");
  await page.getByRole("menuitemradio", { name: "自定义模型" }).click();
  await expect(slider).toHaveValue("1");
  await expect(slider).toBeEnabled();
  await page.getByRole("menuitemradio", { name: "内置模型" }).click();
  await expect(slider).toHaveValue("0");
  await expect(slider).toBeEnabled();
  await slider.press("ArrowRight");
  await expect(page.getByRole("status", { name: "思考强度保存状态" })).toHaveText("已应用");
  await page.getByRole("button", { name: "恢复默认强度" }).click();
  await expect(slider).toBeEnabled();
  await expect(slider).toHaveValue("0");
  expect(await page.evaluate(() => (window as unknown as { __modelManagerFixture: Fixture }).__modelManagerFixture.settingsCalls)).toEqual([
    { reasoning_effort: "max" }, { reasoning_effort: "low" }, { reasoning_effort: "" },
  ]);
});

test("快捷思考滑块拖动结束只保存一次，窄窗口可操作", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 380, height: 700 });
  const slider = await openMenu(page);
  const bounds = await slider.boundingBox();
  expect(bounds).not.toBeNull();
  const { x, y, width, height } = bounds!;
  expect(x).toBeGreaterThanOrEqual(0);
  expect(x + width).toBeLessThanOrEqual(380);
  await page.mouse.move(x + 8, y + height / 2);
  await page.mouse.down();
  await page.mouse.move(x + 16 + (width - 32) * 0.6, y + height / 2, { steps: 12 });
  expect(await page.evaluate(() => (window as unknown as { __modelManagerFixture: Fixture }).__modelManagerFixture.settingsCalls.length)).toBe(0);
  await page.mouse.up();
  await expect(page.getByRole("status", { name: "思考强度保存状态" })).toHaveText("已应用");
  await expect(slider).toHaveValue("3");
  expect(await page.evaluate(() => (window as unknown as { __modelManagerFixture: Fixture }).__modelManagerFixture.settingsCalls)).toEqual([{ reasoning_effort: "high" }]);
  await page.screenshot({ path: testInfo.outputPath("reasoning-menu-mobile.png") });
});

test("快捷思考滑块保存期间禁用切换，失败回滚且可重试", async ({ page }) => {
  const slider = await openMenu(page);
  await page.evaluate(() => {
    const fixture = (window as unknown as { __modelManagerFixture: Fixture }).__modelManagerFixture;
    fixture.setSettingsError(true);
    fixture.setSettingsDelay(500);
  });
  await slider.press("End");
  await expect(slider).toBeDisabled();
  await expect(page.getByRole("menuitemradio", { name: "自定义模型" })).toBeDisabled();
  await expect(page.getByRole("alert")).toHaveText("思考强度保存失败");
  await expect(slider).toHaveValue("0");
  await expect(slider).toBeEnabled();
  await page.evaluate(() => (window as unknown as { __modelManagerFixture: Fixture }).__modelManagerFixture.setSettingsError(false));
  await slider.press("ArrowRight");
  await expect(page.getByRole("status", { name: "思考强度保存状态" })).toHaveText("已应用");
  await expect(page.getByRole("alert")).toHaveCount(0);
});
