import { expect, test } from "@playwright/test";

test("narrow launcher keeps permission and model menus usable", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const shell = page.locator(".task-launcher .composer-input-shell");
  await shell.evaluate((el) => { el.style.width = "260px"; });
  const toolbar = shell.locator(".composer-toolbar");
  expect(await toolbar.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
  await toolbar.locator(".permission").click();
  await expect(shell.locator(".permission-popover")).toBeVisible();
  await page.keyboard.press("Escape");
  await toolbar.locator(".model-config-trigger").click();
  await expect(shell.locator(".model-picker-popover")).toBeVisible();
});

test("narrow conversation keeps controls in one row and prioritizes statistics", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("#app").evaluate((root) => {
    const state = (root as any).__vue_app__._instance.setupState;
    state.sessions = [{ session_id: "compact", title: "Compact", status: "active", archived: false, updated_at: "", total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0 }];
    state.activeId = "compact";
    state.runtimeSettings = { ...state.runtimeSettings, permission_mode: "auto", model: "DeepSeek-V3.2-Extra-Long-Model-Name" };
    state.timeline = new Map([[1, { step: 1, status: "done", tokens: [], toolCalls: [], runId: "compact-run", runStats: { inputTokens: 10000, outputTokens: 2000, cacheReadTokens: 5000, contextPct: 0.96, llmMs: 25000, ttftMs: 1000 } }]]);
  });
  const pane = page.locator(".task-conversation");
  await expect(pane).toBeVisible();
  for (const width of [760, 450, 330, 280]) {
    await pane.evaluate((el, width) => { el.style.width = `${width}px`; el.style.maxWidth = "none"; }, width);
    const toolbar = pane.locator(".composer-toolbar");
    const layout = await toolbar.evaluate((el) => {
      const buttons = [...el.querySelectorAll<HTMLButtonElement>(":scope > button, :scope > .model-config-control > button")];
      const rect = el.getBoundingClientRect();
      return { width: rect.width, overflow: el.scrollWidth - el.clientWidth, buttons: buttons.map((b) => { const r = b.getBoundingClientRect(); return { left: r.left - rect.left, right: r.right - rect.left, height: r.height, top: r.top }; }) };
    });
    expect(layout.overflow, `width ${width}`).toBeLessThanOrEqual(1);
    for (const button of layout.buttons) {
      expect(button.height).toBeLessThanOrEqual(36);
      expect(button.left).toBeGreaterThanOrEqual(0);
      expect(button.right).toBeLessThanOrEqual(layout.width + 1);
    }
    for (let i = 1; i < layout.buttons.length; i++) expect(layout.buttons[i].left).toBeGreaterThanOrEqual(layout.buttons[i - 1].right);
    if (width <= 450) {
      await expect(pane.locator('[data-kind="tokens"]')).toBeHidden();
      await expect(pane.locator('[data-kind="context"]')).toBeVisible();
      await expect(pane.locator(".session-stats-line")).toHaveAttribute("title", /10/);
    }
    await toolbar.locator(".model-config-trigger").click();
    await expect(pane.locator(".model-picker-popover")).toBeVisible();
    await page.keyboard.press("Escape");
  }
});
