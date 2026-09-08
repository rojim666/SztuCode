import { expect, test, type Locator } from "@playwright/test";

type Theme = "light" | "dark";

function appearance(theme: Theme) {
  return {
    theme,
    wallpaper: "grid",
    wallpaperIntensity: 55,
    chromeTransparency: 32,
    conversationTransparency: 36,
    composerTransparency: 8,
    inspectorTransparency: 36,
  };
}

async function backgroundAlpha(locator: Locator): Promise<number> {
  return locator.evaluate((element) => {
    const color = getComputedStyle(element).backgroundColor;
    if (color === "transparent") return 0;
    const slashAlpha = color.match(/\/\s*([\d.]+)\s*\)$/);
    if (slashAlpha) return Number(slashAlpha[1]);
    const channels = color.match(/[\d.]+/g)?.map(Number) ?? [];
    return channels.length >= 4 ? channels[3] : 1;
  });
}

for (const theme of ["light", "dark"] as const) {
  test(`wallpaper remains visible on automations and skills in ${theme} theme`, async ({ page }) => {
    await page.addInitScript((settings) => {
      localStorage.setItem("sztu.appearance", JSON.stringify(settings));
    }, appearance(theme));
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: /^自动化/ }).click();
    await expect(page.locator(".chat-automations")).toBeVisible();
    await expect.poll(() => backgroundAlpha(page.locator(".sztu-main"))).toBe(0);
    await expect.poll(() => backgroundAlpha(page.locator(".chat-automations"))).toBe(0);

    await page.locator(".chat-automations").getByRole("button", { name: "新建任务", exact: true }).click();
    const automationSurfaceAlpha = await backgroundAlpha(page.locator(".automation-form"));
    expect(automationSurfaceAlpha).toBeGreaterThan(0);
    expect(automationSurfaceAlpha).toBeLessThan(1);
    await expect(page.locator(".automation-form")).toHaveCSS("backdrop-filter", /blur/);

    await page.getByRole("button", { name: "技能", exact: true }).click();
    await expect(page.locator(".skill-center")).toBeVisible();
    await expect.poll(() => backgroundAlpha(page.locator(".sztu-main"))).toBe(0);
    await expect.poll(() => backgroundAlpha(page.locator(".skill-center"))).toBe(0);

    const topbar = page.locator(".skill-center__topbar");
    const topbarAlpha = await backgroundAlpha(topbar);
    expect(topbarAlpha).toBeGreaterThan(0);
    expect(topbarAlpha).toBeLessThanOrEqual(0.3);
    await expect(topbar).toHaveCSS("backdrop-filter", "none");

    const search = page.locator(".skill-search");
    const searchAlpha = await backgroundAlpha(search);
    expect(searchAlpha).toBeGreaterThan(0);
    expect(searchAlpha).toBeLessThan(1);
    await expect(search).toHaveCSS("backdrop-filter", /blur/);
  });
}

