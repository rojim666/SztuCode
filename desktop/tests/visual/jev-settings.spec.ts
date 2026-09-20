import { expect, test } from "@playwright/test";

test("old daemon displays an upgrade hint instead of pretending to save Jev settings", async ({ page }) => {
  await page.goto("/tests/visual/fixtures/jev-settings.html?scenario=legacy");
  const section = page.getByRole("region", { name: "实验性功能" });
  await expect(section.getByRole("alert")).toContainText("当前本地服务版本不支持 Jev 模式");
  await expect(section.getByRole("switch")).toBeDisabled();
  await expect(section.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
});

test("missing credential is explained next to the switch without a failed RPC", async ({ page }) => {
  await page.goto("/tests/visual/fixtures/jev-settings.html");
  const section = page.getByRole("region", { name: "实验性功能" });
  await section.getByRole("switch").click();
  await expect(section.getByRole("alert")).toContainText("请先填写 TypeSafe API Key");
  await expect(section.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  expect(await page.evaluate(() => (window as any).__jevFixture.updates.length)).toBe(0);
});

test("an ignored update keeps the entered key and does not display saved", async ({ page }) => {
  await page.goto("/tests/visual/fixtures/jev-settings.html?scenario=ignored");
  const section = page.getByRole("region", { name: "实验性功能" });
  await section.getByLabel("TypeSafe API Key").fill("test-key");
  await section.getByRole("switch").click();
  await expect(section.getByRole("alert")).toContainText("本地服务未应用 Jev 设置");
  await expect(section.getByLabel("TypeSafe API Key")).toHaveValue("test-key");
  await expect(section.getByRole("status")).toHaveCount(0);
});

for (const width of [1000, 390]) {
  test(`Jev settings save, switch and failure at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/tests/visual/fixtures/jev-settings.html");
    const section = page.getByRole("region", { name: "实验性功能" });
    await section.scrollIntoViewIfNeeded();
    const toggle = section.getByRole("switch", { name: "LLM + Jev Agent 模式" });
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await section.getByLabel("TypeSafe API Key").fill("test-key");
    await section.getByLabel("Jev 模型").fill("jev-1.13.0");
    await section.getByLabel("最低置信度").fill("0.9");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await expect(section.getByLabel("TypeSafe API Key")).toHaveValue("");
    await expect(section.getByLabel("TypeSafe API Key")).toHaveAttribute("placeholder", /已配置/);
    await expect(section.getByRole("status")).toHaveText("已保存");
    const updates = await page.evaluate(() => (window as any).__jevFixture.updates);
    expect(updates[0]).toEqual({ experimental_jev: true, jev_api_key: "test-key", jev_model: "jev-1.13.0", jev_confidence_threshold: 0.9 });
    await section.getByRole("button", { name: "保存", exact: true }).scrollIntoViewIfNeeded();
    await expect(section.getByRole("button", { name: "保存", exact: true }).locator("svg")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`jev-${width}.png`), fullPage: true });
    const bounds = await section.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    for (const input of await section.locator("input").all()) {
      const inputBounds = await input.boundingBox();
      expect(inputBounds!.x + inputBounds!.width).toBeLessThanOrEqual(bounds!.x + bounds!.width + 1);
    }
    await page.evaluate(() => (window as any).__jevFixture.setFailure(true));
    await toggle.click();
    await expect(section.getByRole("alert")).toContainText("Test connection failure");
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await page.evaluate(() => (window as any).__jevFixture.setFailure(false));
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "false");
  });
}
