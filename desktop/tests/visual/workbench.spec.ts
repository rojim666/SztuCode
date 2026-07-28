import { expect, test } from "@playwright/test";

// 功能：验证 1280px 工作台保留三栏信息层级与离线诊断提示。
// 设计：在无 daemon 的浏览器回归环境等待稳定离线状态后截图，避免网络可用性影响视觉基线。
test("desktop workbench baseline", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await expect(page.getByText("本地服务暂不可用")).toBeVisible();
  await expect(page).toHaveScreenshot("workbench-1280.png", { fullPage: true });
});

// 功能：验证 440px 窄屏下任务栏以抽屉打开且主界面不会横向溢出。
// 设计：点击具有 aria 标签的导航按钮后截图，精确覆盖方案要求的小屏任务栏入口而非仅检查 CSS 断点存在。
test("narrow workbench sidebar baseline", async ({ page }) => {
  await page.setViewportSize({ width: 440, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "打开任务栏" }).click();
  await expect(page.getByRole("navigation", { name: "任务历史" })).toBeVisible();
  await expect(page).toHaveScreenshot("workbench-440-sidebar.png", { fullPage: true });
});

// 功能：验证命令面板在默认工作台之上以可读层级呈现。
// 设计：使用 Ctrl+K 触发真实全局快捷键并等待 dialog 语义出现，覆盖键盘优先交互与视觉层级。
test("command palette baseline", async ({ page }) => {
  await page.setViewportSize({ width: 920, height: 900 });
  await page.goto("/");
  await expect(page.getByText("本地服务暂不可用")).toBeVisible();
  await page.keyboard.press("Control+K");
  await expect(page.getByRole("dialog", { name: "命令面板" })).toBeVisible();
  await expect(page).toHaveScreenshot("command-palette-920.png", { fullPage: true });
});

test("settings and provider status baseline", async ({ page }) => {
  await page.setViewportSize({ width: 920, height: 900 });
  await page.goto("/");
  await expect(page.getByText("本地服务暂不可用")).toBeVisible();
  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.getByRole("dialog", { name: "运行设置" })).toBeVisible();
  await expect(page).toHaveScreenshot("settings-provider-920.png", { fullPage: true });
});
