import { expect, test } from "@playwright/test";

test("skills page keeps settings, model management, and window controls interactive", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.getByRole("button", { name: "技能", exact: true }).click();
  await expect(page.getByRole("region", { name: "插件与技能" })).toBeVisible();

  await expect(page.getByRole("button", { name: "Minimize window" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Maximize or restore window" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Close window" })).toBeEnabled();

  await page.getByRole("button", { name: "设置", exact: true }).click();
  const settings = page.getByRole("dialog", { name: "设置" });
  await expect(settings).toBeVisible();
  await settings.getByRole("button", { name: "模型管理", exact: true }).click();
  await expect(settings.getByRole("heading", { name: "模型管理", exact: true })).toBeVisible();
  await settings.getByRole("button", { name: "关闭设置" }).click();
  await expect(settings).toBeHidden();
});

test("skill center supports descriptions, local installs, and delete affordances", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/tests/visual/fixtures/skill-center.html", { waitUntil: "domcontentloaded" });
  const skillCenter = page.getByRole("region", { name: "插件与技能" });
  await expect(skillCenter).toBeVisible();
  await skillCenter.getByRole("button", { name: "技能", exact: true }).click();
  await expect(skillCenter.getByRole("heading", { name: "技能", exact: true })).toBeVisible();

  await page.getByPlaceholder("搜索技能").fill("frontend");
  const catalogRow = skillCenter.locator(".skill-card");
  await expect(catalogRow).toHaveCount(1);
  await expect(catalogRow.locator(".skill-name")).toHaveText("frontend-design");
  await catalogRow.click();
  const detailDialog = page.getByRole("dialog", { name: "frontend-design" });
  await expect(detailDialog.getByRole("heading", { name: "技能描述" })).toBeVisible();
  await expect(detailDialog.getByText("设计并实现高质量、可交付的前端界面与交互")).toBeVisible();
  await detailDialog.getByRole("button", { name: "关闭" }).click();
  await page.getByPlaceholder("搜索技能").fill("");

  await page.getByRole("button", { name: "添加", exact: true }).click();
  await page.getByRole("button", { name: /添加技能/ }).click();
  const installDialog = page.getByRole("dialog", { name: "添加技能" });
  await expect(installDialog).toBeVisible();
  await installDialog.getByPlaceholder("选择插件/技能目录").fill("./skills/release-notes");
  await installDialog.getByRole("button", { name: "安装", exact: true }).click();
  await expect(installDialog).toBeHidden();
  await page.getByPlaceholder("搜索技能").fill("release-notes");
  await expect(skillCenter.locator(".skill-card")).toHaveCount(1);
  await expect(skillCenter.locator(".skill-card .skill-name")).toHaveText("release-notes");
  await skillCenter.locator(".skill-card").click();
  const installedDetail = page.getByRole("dialog", { name: "release-notes" });
  await expect(installedDetail.getByRole("heading", { name: "技能描述" })).toBeVisible();
  await expect(installedDetail.getByRole("button", { name: "删除技能" })).toBeVisible();
  await installedDetail.getByRole("button", { name: "关闭" }).click();
  await page.getByPlaceholder("搜索技能").fill("");
  await expect(page).toHaveScreenshot("skill-center-component-1280.png", { fullPage: true });
});
