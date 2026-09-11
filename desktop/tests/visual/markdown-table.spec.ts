import { expect, test } from "@playwright/test";

for (const component of ["timeline/TokenStream", "Inspector/RichFilePreview"]) {
  test(`${component}: tables fill their frame and wide content scrolls locally`, async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.evaluate(async (name) => {
      const vueUrl = "/node_modules/.vite/deps/vue.js";
      const { createApp, h } = await import(vueUrl);
      const { default: Component } = await import(`/src/components/${name}.vue`);
      const host = document.createElement("div");
      host.id = "table-fixture";
      host.style.cssText = "position:fixed;inset:0 auto auto 0;width:810px;background:white;z-index:9999";
      document.body.append(host);
      const markdown = "| 提交 | 说明 |\n| --- | --- |\n| `24c9999` | feat(runtime): 精确编辑的不可变文件版本历史 |\n| `ed160bc` | feat(runtime): 可选的 smart 模型路由 |";
      const app = createApp({ render: () => h(Component, { tokens: [], finalText: markdown, path: "test.md", content: markdown }) });
      const i18nUrl = "/src/i18n/index.ts";
      const { i18n } = await import(i18nUrl);
      app.use(i18n);
      app.mount(host);
    }, component);
    const frame = page.locator("#table-fixture .markdown-table-scroll");
    await expect(frame).toBeVisible();
    for (const theme of ["light", "dark"]) {
      await page.locator("html").evaluate((el, value) => { el.dataset.appTheme = value; }, theme);
      const widths = await frame.evaluate((el) => ({
        frame: el.clientWidth,
        header: el.querySelector("thead")!.getBoundingClientRect().width,
        row: el.querySelector("tbody tr")!.getBoundingClientRect().width,
        display: getComputedStyle(el.querySelector("table")!).display,
      }));
      expect(widths.display).toBe("table");
      expect(Math.abs(widths.frame - widths.header)).toBeLessThanOrEqual(1);
      expect(Math.abs(widths.frame - widths.row)).toBeLessThanOrEqual(1);
    }
    await page.locator("#table-fixture").evaluate((el) => { el.style.width = "280px"; });
    await frame.locator("td").first().evaluate((el) => { el.textContent = "long-column-".repeat(50); (el as HTMLElement).style.whiteSpace = "nowrap"; });
    const overflow = await frame.evaluate((el) => {
      el.scrollLeft = 100;
      return { width: el.getBoundingClientRect().width, scrollWidth: el.scrollWidth, scrollLeft: el.scrollLeft };
    });
    expect(overflow.width).toBeLessThanOrEqual(280);
    expect(overflow.scrollWidth).toBeGreaterThan(280);
    expect(overflow.scrollLeft).toBeGreaterThan(0);
    await expect(frame).toHaveAttribute("tabindex", "0");
  });
}
