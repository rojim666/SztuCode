import { test } from "@playwright/test";

test("tooltip element screenshot", async ({ page }) => {
  await page.goto("/");
  const toggle = page.getByRole("button", { name: "收起导航" });
  await toggle.hover();
  await page.waitForTimeout(400);
  const tip = page.locator(".nav-toggle-tooltip");
  await tip.screenshot({ path: "tests/visual/_tmp_tooltip_now.png" });
  const s = await tip.evaluate((el) => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const menu = document.querySelector(".app-menu-bar")?.getBoundingClientRect();
    return { zIndex: cs.zIndex, box: { x: r.x, y: r.y, w: r.width, h: r.height }, menuBar: menu ? { x: menu.x, y: menu.y, w: menu.width, h: menu.height } : null, overlap: menu ? !(r.right <= menu.left || r.left >= menu.right || r.bottom <= menu.top || r.top >= menu.bottom) : false };
  });
  console.log("TOOLTIP_OVERLAP " + JSON.stringify(s));
});
