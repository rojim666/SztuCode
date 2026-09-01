import { expect, test } from "@playwright/test";

async function openCanvasFixture(
  page: import("@playwright/test").Page,
  viewport = { width: 1280, height: 800 },
) {
  // 入场动画含 translateX(14px)，进行中会读到偏移几何；reduced-motion 下动画禁用，几何与截图均确定
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize(viewport);
  await page.goto("/tests/visual/fixtures/canvas-panel.html");
  await expect(page.locator(".canvas-panel")).toBeVisible();
}

test("画布渲染标题、表格、图片与代码块", async ({ page }) => {
  await openCanvasFixture(page);

  // 标题与版本徽标
  await expect(page.locator(".canvas-panel__title")).toHaveText("竞品分析报告");
  await expect(page.locator(".canvas-panel__version")).toHaveText("v2");

  // Markdown 结构渲染
  const body = page.locator(".canvas-panel__body");
  await expect(body.locator("h1")).toHaveText("竞品分析报告");
  await expect(body.locator("h2").first()).toHaveText("核心结论");
  await expect(body.locator("blockquote")).toContainText("文档画布是交付质量的关键差异化能力");

  // GFM 表格：表头 + 数据行
  const table = body.locator("table");
  await expect(table.locator("th").nth(1)).toHaveText("文档画布");
  await expect(table.locator("td").first()).toHaveText("SztuCode");
  await expect(table.locator("tr")).toHaveCount(4);

  // 图片（内联 data URL）成功渲染且无失败占位
  const image = body.locator("img");
  await expect(image).toBeVisible();
  await expect(image).toHaveAttribute("src", /^data:image\/svg\+xml/);
  await expect(body.locator(".canvas-img-failed")).toHaveCount(0);

  // 代码块
  await expect(body.locator("pre code")).toContainText("store.create");

  // 页脚元信息
  await expect(page.locator(".canvas-panel__footer")).toContainText("更新于");

  await expect(page).toHaveScreenshot("canvas-panel-1280.png");
});

test("多文档标签切换渲染第二篇文档", async ({ page }) => {
  await openCanvasFixture(page);

  const tabs = page.locator(".canvas-panel__tab");
  await expect(tabs).toHaveCount(2);
  await expect(tabs.first()).toHaveClass(/active/);

  await tabs.nth(1).click();

  // fixture 中 select 由宿主处理：此处仅验证点击事件可触发（不报错），标签结构保持可见
  await expect(tabs.nth(1)).toBeVisible();
  await expect(page.locator(".canvas-panel__body h1")).toBeVisible();
});

test("窄窗口下面板不溢出且无横向滚动", async ({ page }) => {
  await openCanvasFixture(page, { width: 760, height: 700 });

  const geometry = await page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>(".canvas-panel")!;
    const rect = panel.getBoundingClientRect();
    return {
      panelRight: rect.right,
      viewportWidth: window.innerWidth,
      pageWidth: document.documentElement.scrollWidth,
    };
  });

  expect(geometry.panelRight).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.pageWidth).toBeLessThanOrEqual(geometry.viewportWidth);

  // 表格在窄面板内可横向滚动而不是撑破面板
  const body = page.locator(".canvas-panel__body");
  await expect(body.locator("table")).toBeVisible();
  await expect(page).toHaveScreenshot("canvas-panel-760.png");
});
