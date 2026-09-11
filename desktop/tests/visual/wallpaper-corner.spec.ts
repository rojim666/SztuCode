import { expect, test } from "@playwright/test";
import sharp from "sharp";

test("chrome opacity does not cover the transparent workspace", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("html").evaluate((root) => {
    root.dataset.wallpaper = "custom";
    root.dataset.appTheme = "light";
    root.style.setProperty("--custom-wallpaper-image", "linear-gradient(#e03060, #e03060)");
    root.style.setProperty("--wallpaper-opacity", "1");
    root.style.setProperty("--conversation-surface-opacity", "0%");
  });
  const sample = async () => {
    const bounds = await page.locator(".sztu-main").boundingBox();
    if (!bounds) throw new Error("Missing workspace");
    return [...await sharp(await page.screenshot({ animations: "disabled" })).extract({ left: Math.ceil(bounds.x + 60), top: Math.ceil(bounds.y + 90), width: 1, height: 1 }).removeAlpha().raw().toBuffer()];
  };
  for (const opacity of ["0%", "50%", "100%"]) {
    await page.locator("html").evaluate((root, value) => root.style.setProperty("--chrome-surface-opacity", value), opacity);
    expect(await sample(), `chrome ${opacity} must not dim the workspace`).toEqual([224, 48, 96]);
  }
  await page.locator("html").evaluate((root) => root.style.setProperty("--conversation-surface-opacity", "100%"));
  expect(await sample()).not.toEqual([224, 48, 96]);
  await page.locator("html").evaluate((root) => root.style.setProperty("--conversation-surface-opacity", "0%"));
  expect(await sample()).toEqual([224, 48, 96]);
});

test("wallpaper changes keep the clipped corner continuous with chrome", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  for (const theme of ["light", "dark"]) {
    for (const wallpaper of ["none", "mist", "grid", "paper", "custom", "none"]) {
      await page.locator("html").evaluate((root, { theme, wallpaper }) => {
        root.dataset.appTheme = theme;
        root.dataset.wallpaper = wallpaper;
        root.style.setProperty("--custom-wallpaper-image", "linear-gradient(120deg, #c45b31, #217daa)");
      }, { theme, wallpaper });
      const bounds = await page.locator(".sztu-main").boundingBox();
      if (!bounds) throw new Error("Missing workspace");
      const { data, info } = await sharp(await page.screenshot({ animations: "disabled" })).removeAlpha().raw().toBuffer({ resolveWithObject: true });
      const x = Math.ceil(bounds.x), y = Math.ceil(bounds.y);
      const pixel = (px: number, py: number) => [...data.subarray((py * info.width + px) * info.channels, (py * info.width + px) * info.channels + 3)];
      const corner = pixel(x, y);
      for (const adjacent of [pixel(x - 2, y), pixel(x, y - 2)]) {
        expect(Math.max(...corner.map((v, i) => Math.abs(v - adjacent[i]))), `${theme}/${wallpaper}: corner seam`).toBeLessThanOrEqual(3);
      }
    }
  }
});
