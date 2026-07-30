import { expect, test } from "@playwright/test";

test("Kimi Work shell renders the new task entry", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await expect(page.getByRole("tablist", { name: "工作模式" })).toBeVisible();
  await expect(page.getByRole("button", { name: /新建任务/ })).toBeVisible();
  await expect(page).toHaveScreenshot("kimi-work-1280.png", { fullPage: true });
});

test("scheduled task page communicates its daemon integration state", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await page.getByRole("button", { name: "定时任务" }).click();
  await expect(page.getByRole("heading", { name: "定时任务", exact: true })).toBeVisible();
  await expect(page.getByText("暂无定时任务")).toBeVisible();
  await expect(page).toHaveScreenshot("kimi-automations-1280.png", { fullPage: true });
});

test("settings mirrors the Kimi Work settings layout", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await page.locator(".settings-link").click();
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  await expect(page.getByText("系统设置")).toBeVisible();
  await expect(page).toHaveScreenshot("kimi-settings-1280.png", { fullPage: true });
});
