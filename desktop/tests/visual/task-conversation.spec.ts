import { expect, test } from "@playwright/test";

test("task conversation prioritizes outcome, evidence, and optional work records", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/tests/visual/fixtures/task-conversation.html");

  const verifiedLabels = page.getByText("已完成并验证", { exact: true });
  await expect(verifiedLabels).toHaveCount(0);
  const resultRegions = page.getByRole("region", { name: "任务结果" });
  await expect(resultRegions).toHaveCount(2);
  await expect(resultRegions.nth(0)).toBeVisible();
  const evidenceRegions = page.getByRole("region", { name: "验证与变更" });
  await expect(evidenceRegions).toHaveCount(0);
  await expect(page.getByText("等待授权", { exact: true })).toBeVisible();
  await expect(page.getByText("正在项目中定位代码", { exact: true })).toBeVisible();
  await expect(page.getByText("第一次命令不可用，我已切换到项目中存在的测试入口并完成验证。", { exact: true })).toBeVisible();
  await expect(page.getByText("我先检查了登录拦截器和路由守卫的职责边界。", { exact: true })).toHaveCount(0);
  await expect(page.getByText("执行遇到问题", { exact: true })).toHaveCount(0);

  const historyToggles = page.locator(".turn-history-toggle");
  await expect(historyToggles).toHaveCount(4);
  await expect(page.locator(".turn-history")).toHaveCount(0);
  await expect(page.locator(".turn-call-summary")).toHaveCount(2);
  await expect(page.getByText("已运行 1 项操作", { exact: true }).first()).toBeVisible();
  await historyToggles.first().click();
  await historyToggles.nth(1).click();
  await expect(page.locator(".turn-history")).toHaveCount(2);
  const groupedOperations = page.locator(".tool-call-group");
  await expect(groupedOperations).toHaveCount(1);
  const groupedOperationsTrigger = groupedOperations.getByRole("button").first();
  await expect(groupedOperationsTrigger).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: /session expired/ })).toHaveCount(0);
  await groupedOperationsTrigger.click();
  await expect(groupedOperationsTrigger).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("我先检查了登录拦截器和路由守卫的职责边界。", { exact: true })).toBeVisible();
  await expect(verifiedLabels).toHaveCount(2);
  await expect(page.locator(".evidence-strip")).toHaveCount(2);
  const turnTokenTotals = await page.locator(".turn-usage b").allTextContents();
  expect(turnTokenTotals).toHaveLength(2);
  expect(new Set(turnTokenTotals).size).toBe(turnTokenTotals.length);
  await expect(page.getByText("命中缓存 9.3K", { exact: true })).toBeVisible();
  // 用类名定位：复制成功后按钮名称会变为“已复制总结”，按名称定位会滑到下一个按钮
  const copySummary = page.locator(".turn-copy").first();
  await expect(copySummary).toBeVisible();
  await copySummary.click();
  await expect(copySummary).toHaveAttribute("aria-label", "已复制总结");
  await expect(page.getByRole("button", { name: /已搜索 session expired/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /已编辑 src\/auth\/session.ts/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /已运行 npm test -- auth/ }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "过程说明" })).toBeVisible();
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
