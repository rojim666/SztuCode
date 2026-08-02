import { expect, test } from "@playwright/test";

test("Chat portal exposes every tool page and its primary interactions", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await page.getByRole("button", { name: "Chat", exact: true }).click();

  const nav = page.locator(".chat-sidebar .primary-nav");
  await expect(page.getByPlaceholder("输入 / 唤起插件和技能")).toBeVisible();

  await nav.getByRole("button", { name: "插件", exact: true }).click();
  await expect(page.getByRole("heading", { name: "插件", exact: true })).toBeVisible();
  await page.getByPlaceholder("搜索插件").fill("Stripe");
  await expect(page.locator(".plugin-card")).toHaveCount(1);

  await nav.getByRole("button", { name: "定时任务", exact: true }).click();
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await page.getByPlaceholder("例如：每周项目进展汇总").fill("周报汇总");
  await page.getByRole("button", { name: "保存任务", exact: true }).click();
  await expect(page.getByText("暂无定时任务")).toBeVisible();

  const tools = [
    ["PPT", "输入你想创作的 PPT 主题"],
    ["集群", "给 AI 团队派个活..."],
    ["深度研究", "描述你的问题，生成深度研究报告"],
    ["文档", "上传文档进行编辑，或从零开始创建"],
    ["网站", "描述你的网站想法，风格、功能、数据库都可以"],
    ["表格", "上传表格进行分析，或从零开始创建"],
  ] as const;
  for (const [label, placeholder] of tools) {
    await nav.getByRole("button", { name: label, exact: true }).click();
    await expect(page.getByPlaceholder(placeholder)).toBeVisible();
    await expect(page.locator(".template-preview").first()).toBeVisible();
  }

  await page.getByRole("button", { name: "新建项目", exact: true }).click();
  await page.getByPlaceholder("取个名字").fill("产品调研");
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(page.getByRole("heading", { name: "产品调研 已创建" })).toBeVisible();
});
