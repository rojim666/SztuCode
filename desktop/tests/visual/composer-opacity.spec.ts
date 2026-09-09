import { expect, test } from "@playwright/test";
import sharp from "sharp";

for (const theme of ["light", "dark"]) {
  test(`${theme}: input transparency slider changes the actual conversation card`, async ({ page }) => {
    await page.addInitScript((theme) => localStorage.setItem("sztu.appearance", JSON.stringify({ theme, wallpaper: "custom", customWallpaper: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><path fill="#e03060" d="M0 0h10v10H0z"/></svg>'), wallpaperIntensity: 70, composerTransparency: 0 })), theme);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.locator("#app").evaluate((root) => {
      const state = (root as any).__vue_app__._instance.setupState;
      state.sessions = [{ session_id: "opacity", title: "Opacity", status: "active", archived: false, updated_at: "", total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0 }];
      state.activeId = "opacity";
    });
    const card = page.locator(".task-conversation .sztu-composer");
    const samples: number[][] = [];
    for (const transparency of [0, 40, 80]) {
      await page.getByRole("button", { name: "设置", exact: true }).click();
      const slider = page.getByRole("slider", { name: "输入框透明度", exact: true });
      await slider.fill(String(transparency));
      await expect(page.locator("html")).toHaveAttribute("style", new RegExp(`--composer-surface-opacity: ${100 - transparency}%`));
      await page.getByRole("button", { name: "关闭设置" }).click();
      const colors = await card.evaluate((el) => ({
        fill: getComputedStyle(el).backgroundColor,
        inner: getComputedStyle(el.querySelector(".composer-input-shell")!).backgroundColor,
        queue: getComputedStyle(el.parentElement!).backgroundColor,
      }));
      expect(colors.inner).toBe("rgba(0, 0, 0, 0)");
      expect(colors.queue).toBe("rgba(0, 0, 0, 0)");
      if (transparency) expect(colors.fill).toContain(`/ ${((100 - transparency) / 100).toFixed(1)})`);
      const bounds = await card.boundingBox();
      if (!bounds) throw new Error("Missing input card");
      samples.push([...await sharp(await page.screenshot({ animations: "disabled" })).extract({ left: Math.round(bounds.x + bounds.width / 2), top: Math.round(bounds.y + 55), width: 1, height: 1 }).removeAlpha().raw().toBuffer()]);
    }
    expect(samples[0]).not.toEqual(samples[1]);
    expect(samples[1]).not.toEqual(samples[2]);
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem("sztu.appearance")!).composerTransparency)).toBe(80);
  });
}
