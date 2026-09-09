import { expect, test } from "@playwright/test";

test("launcher bottom strip retains its own fill when wallpaper changes", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const strip = page.locator(".task-launcher .launcher-bottom-controls");
  for (const theme of ["light", "dark"]) {
    for (const wallpaper of ["none", "mist", "grid", "paper", "custom", "none"]) {
      await page.locator("html").evaluate((el, { theme, wallpaper }) => {
        el.dataset.appTheme = theme;
        el.dataset.wallpaper = wallpaper;
        el.style.setProperty("--composer-surface-opacity", "20%");
      }, { theme, wallpaper });
      await expect(strip).toHaveCSS("background-color", theme === "light" ? "rgb(245, 245, 245)" : "rgb(37, 37, 37)");
      if (wallpaper !== "none") {
        await expect(page.locator(".task-launcher .composer-input-shell")).toHaveCSS("background-color", theme === "light" ? "color(srgb 1 1 1 / 0.2)" : "color(srgb 0.0901961 0.0901961 0.0901961 / 0.2)");
      }
    }
  }
  await strip.locator(".composer-project").click();
  await expect(page.locator(".project-picker-popover")).toBeVisible();
});
