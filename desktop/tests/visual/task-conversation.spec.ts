import { expect, test } from "@playwright/test";

test("task conversation prioritizes outcome, evidence, and optional work records", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/tests/visual/fixtures/task-conversation.html");

  await expect(page.getByText("等待权限审批", { exact: true })).toBeVisible();
  await expect(page.getByText("步骤 2 / 3", { exact: true })).toBeVisible();
  await expect(page.getByText("第一次命令不可用，我已切换到项目中存在的测试入口并完成验证。", { exact: true })).toBeVisible();
  await expect(page.getByText("我先检查了登录拦截器和路由守卫的职责边界。", { exact: true })).toHaveCount(0);

  const historyToggles = page.locator(".turn-history-toggle");
  await expect(historyToggles).toHaveCount(2);
  await expect(page.locator(".evidence-strip")).toHaveCount(0);
  await historyToggles.first().click();
  await historyToggles.nth(1).click();
  await expect(page.locator(".evidence-strip")).toHaveCount(2);
  const activityPhases = page.locator(".activity-phase__trigger");
  await expect(activityPhases).toHaveCount(4);
  await activityPhases.first().click();
  await expect(page.getByText("我先检查了登录拦截器和路由守卫的职责边界。", { exact: true })).toBeVisible();
  const turnTokenTotals = await page.locator(".turn-usage strong").allTextContents();
  expect(turnTokenTotals).toHaveLength(2);
  expect(new Set(turnTokenTotals).size).toBe(turnTokenTotals.length);
  await expect(page.getByLabel("本轮 Token 消耗与缓存命中").first()).toContainText("缓存9.3K");
  const copySummary = page.locator(".turn-actions").first().getByRole("button").first();
  await expect(copySummary).toBeVisible();
  await copySummary.click();
  await expect(copySummary).toHaveAttribute("aria-label", "已复制总结");
  await expect(page.getByText("src/auth/session.ts", { exact: true })).toBeVisible();
  await expect(page.getByText("npm test -- auth", { exact: true })).toHaveCount(2);
});

test("task conversation remains readable in a narrow window", async ({ page }) => {
  await page.setViewportSize({ width: 440, height: 820 });
  await page.goto("/tests/visual/fixtures/task-conversation.html");

  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
    evidenceColumns: document.querySelector(".evidence-strip") ? getComputedStyle(document.querySelector(".evidence-strip")!).gridTemplateColumns : "none",
  }));
  expect(layout.content).toBeLessThanOrEqual(layout.viewport);
  expect(layout.evidenceColumns).toBe("none");
  await expect(page.getByRole("button", { name: "允许一次" })).toBeVisible();
});
