import { expect, test } from "@playwright/test";

test("user question composer submits stable structured answers", async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 720 });
  await page.goto("/tests/visual/fixtures/user-questions.html");

  await expect(page.getByRole("heading", { name: "使用哪种界面方案？" })).toBeVisible();
  await expect(page.getByText("推荐", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: /深色/ }).click();
  await page.getByRole("button", { name: "下一题", exact: true }).last().click();
  await page.getByRole("checkbox", { name: /单元测试/ }).click();
  await page.getByRole("checkbox", { name: /类型检查/ }).click();
  await page.getByRole("button", { name: "提交回答" }).click();

  await expect(page.getByTestId("answer")).toContainText('"id":"theme","selected":["深色 (Recommended)"]');
  await expect(page.getByTestId("answer")).toContainText('"id":"checks","selected":["单元测试","类型检查"]');
});

test("user question composer stays inside a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 720 });
  await page.goto("/tests/visual/fixtures/user-questions.html");

  const geometry = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
    composer: document.querySelector<HTMLElement>(".user-question-composer")?.getBoundingClientRect().width ?? 0,
  }));
  expect(geometry.content).toBeLessThanOrEqual(geometry.viewport);
  expect(geometry.composer).toBeLessThanOrEqual(geometry.viewport - 20);
  await expect(page.getByRole("button", { name: "停止任务" })).toBeVisible();
});
