import { expect, test } from "@playwright/test";

test("git graph renders dense history, refs, and connected lanes", async ({ page }) => {
  await page.setViewportSize({ width: 1180, height: 620 });
  await page.goto("/tests/visual/fixtures/git-graph.html");

  await expect(page.locator(".git-graph-row")).toHaveCount(7);
  await expect(page.locator(".git-graph-refs .ref-remote")).toHaveCount(2);
  await expect(page.locator(".git-graph-refs .ref-tag")).toHaveText("v0.4.0");
  await expect(page.locator(".git-graph-outgoing")).toContainText("传出的更改");
  await expect(page.getByRole("button", { name: "加载更早的提交" })).toBeVisible();
  await page.getByRole("button", { name: "加载更早的提交" }).click();
  await expect.poll(() => page.evaluate(() => (globalThis as typeof globalThis & { __gitGraphLoadMore: number }).__gitGraphLoadMore)).toBe(1);
  expect(await page.locator(".git-graph-canvas path").count()).toBeGreaterThan(7);

  const connectedRows = await page.locator(".git-graph-row").evaluateAll((rows) => rows.map((row) => {
    const paths = [...row.querySelectorAll("path")].map((path) => path.getAttribute("d") ?? "");
    const upperLanes = paths.filter((path) => /M (\d+) 0 L \1 17$/.test(path)).length;
    const lowerLanes = paths.filter((path) => path.includes(" 17 C ")).length;
    return { upperLanes, lowerLanes };
  }));
  expect(connectedRows.some((row) => row.upperLanes > 1 && row.lowerLanes > 1)).toBeTruthy();

  const layout = await page.locator(".git-graph").evaluate((root) => {
    const rows = [...root.querySelectorAll<HTMLElement>(".git-graph-row")];
    return {
      graphHeight: root.getBoundingClientRect().height,
      rowHeights: rows.map((row) => row.getBoundingClientRect().height),
      overflow: root.scrollWidth > root.clientWidth,
    };
  });
  expect(layout.graphHeight).toBeGreaterThan(300);
  expect(layout.rowHeights.every((height) => height === 34)).toBeTruthy();
  expect(layout.overflow).toBeFalsy();
});
