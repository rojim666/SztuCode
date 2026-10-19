import { expect, test } from "@playwright/test";

test("工具图片可打开大图、切换和按 Escape 关闭", async ({ page }) => {
  await page.goto("/tests/visual/fixtures/tool-image.html");
  const thumbnail = page.locator(".tool-call-event__images img").first();
  await expect(thumbnail).toBeVisible();
  await thumbnail.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("1 / 2");
  await page.keyboard.press("ArrowRight");
  await expect(dialog).toContainText("2 / 2");
  await page.screenshot({ path: "test-results/issue-144-tool-lightbox.png" });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});
