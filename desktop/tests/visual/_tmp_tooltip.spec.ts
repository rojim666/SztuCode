import { test } from "@playwright/test";

test("identify what overlaps the tooltip", async ({ page }) => {
  await page.goto("/");
  const toggle = page.getByRole("button", { name: "收起导航" });
  await toggle.hover();
  await page.waitForTimeout(400);
  const tip = page.locator(".nav-toggle-tooltip");
  const box = await tip.boundingBox();
  if (!box) return;
  const info = await tip.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const hit = document.elementFromPoint(cx, cy);
    const collect = (n: Element | null) => {
      const out = [];
      while (n) {
        const s = getComputedStyle(n);
        out.push({ tag: n.tagName, cls: String(n.className).slice(0, 60), txt: (n.textContent || "").slice(0, 20), z: s.zIndex, pos: s.position, bg: s.backgroundColor, color: s.color });
        n = n.parentElement;
      }
      return out;
    };
    const tipRect = el.getBoundingClientRect();
    const overlapping = document.elementsFromPoint(cx, cy).map((n) => {
      const nr = n.getBoundingClientRect();
      return { tag: n.tagName, cls: String(n.className).slice(0, 60), txt: (n.textContent || "").slice(0, 16), z: getComputedStyle(n).zIndex, overlap: !(nr.right <= tipRect.left || nr.left >= tipRect.right || nr.bottom <= tipRect.top || nr.top >= tipRect.bottom) };
    });
    return { hit: collect(hit).slice(0, 6), topMostStack: overlapping.slice(0, 8) };
  });
  console.log("OVERLAP_INFO " + JSON.stringify(info));
});
