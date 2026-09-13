import { expect, test, type Page } from "@playwright/test";

async function seed(page: Page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("#app").evaluate(root => {
    const state = (root as HTMLElement & { __vue_app__: { _instance: { setupState: Record<string, unknown> } } }).__vue_app__._instance.setupState;
    const workspace = { workspace_id: "workspace-context", name: "Context", path: "F:/context", archived: false };
    state.workspace = workspace;
    state.workspaces = [workspace];
    state.sessions = [{ session_id: "session-context", title: "Context", status: "active", updated_at: "", archived: false, pinned: false, workspace_id: "workspace-context", total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0 }];
    state.activeId = "session-context";
    state.activeRunId = "run-context";
    state.runActive = false;
    state.timeline = new Map([[1, {
      step: 1, status: "done", runId: "run-context", userMessage: "检查上下文演进", tokens: [],
      toolCalls: Array.from({ length: 55 }, (_, i) => ({ id: "read-" + i, name: "read_file", params: { path: "src/file-" + i + ".ts" }, status: "done", output: "content" })),
      contextInjections: [
        { id: "s1", source: "system", label: "初始上下文", text: "alpha\nbeta\n M unread.ts", preview: "alpha", chars: 23 },
        { id: "s2", source: "system", label: "第二份上下文", text: "beta\nalpha\n M unread.ts", preview: "beta", chars: 23 },
      ],
    }]]);
  });
  await page.locator(".ctx-row__trigger").click();
}

test("context snapshots preserve history selection and support full text and exact copying", async ({ page }) => {
  await seed(page);
  const row = page.locator(".ctx-row");
  await expect(row.locator(".ctx-row__turn.selected")).toContainText("快照 2");
  await expect(row.locator(".ctx-diff-added")).toHaveCount(1);
  await expect(row.locator(".ctx-diff-removed")).toHaveCount(1);
  await row.getByRole("button", { name: "完整内容", exact: true }).click();
  await expect(row.locator("pre")).toContainText("beta\nalpha");
  await row.getByRole("button", { name: "复制原文", exact: true }).click();
  await expect(row.getByRole("status")).toHaveText("已复制");
  // Windows clipboard normalizes line endings to CRLF.
  expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n")).toBe("beta\nalpha\n M unread.ts");
  await row.locator(".ctx-row__turn").first().click();
  await page.locator("#app").evaluate(root => {
    const state = (root as HTMLElement & { __vue_app__: { _instance: { setupState: { timeline: Map<number, Record<string, unknown>> } } } }).__vue_app__._instance.setupState;
    const step = state.timeline.get(1)!;
    state.timeline = new Map([[1, { ...step, contextInjections: [...step.contextInjections as unknown[], { id: "s3", source: "system", label: "最新上下文", text: "latest", chars: 6, preview: "latest" }] }]]);
  });
  await expect(row.locator(".ctx-row__turn.selected")).toContainText("快照 1");
  await row.getByRole("button", { name: "回到最新", exact: true }).click();
  await expect(row.locator("pre")).toHaveText("latest\n");
  await expect(row.locator(".ctx-row__turn.selected")).toContainText("快照 3");
});

test("read files can be searched beyond the former 48-file limit and do not include Git paths", async ({ page }) => {
  await seed(page);
  const row = page.locator(".ctx-row");
  await expect(row.locator(".ctx-row__file-chip")).toHaveCount(12);
  await row.getByRole("searchbox").fill("file-54.ts");
  await expect(row.locator(".ctx-row__file-chip")).toHaveCount(1);
  await expect(row.locator(".ctx-row__file-chip")).toContainText("src/file-54.ts");
  await row.getByRole("searchbox").fill("unread.ts");
  await expect(row.locator(".ctx-row__file-chip")).toHaveCount(0);
  await expect(row).toContainText("没有匹配的已读文件");
  await row.getByRole("searchbox").clear();
  await row.getByRole("button", { name: /显示更多文件/ }).click();
  await expect(row.locator(".ctx-row__file-chip")).toHaveCount(36);
});

test("read file records open the workspace file tree instead of the task summary", async ({ page }) => {
  await seed(page);
  await page.locator(".ctx-row__file-chip", { hasText: "file-0.ts" }).click();
  const inspector = page.locator(".project-inspector");
  await expect(inspector).toBeVisible();
  await expect(inspector.locator(".workspace-open-tab.active")).toHaveText("文件");
  await expect(inspector.locator(".file-tab.active .file-tab-name")).toHaveText("file-0.ts");
  // 已读文件不是变更文件：不应落到任务摘要页
  await expect(inspector.locator(".task-summary-view")).toHaveCount(0);
  await expect(inspector.locator(".workspace-open-tab", { hasText: "任务摘要" })).toHaveCount(0);
});

test("context panel fits narrow layouts in both themes", async ({ page }) => {
  await page.setViewportSize({ width: 680, height: 900 });
  await seed(page);
  for (const theme of ["light", "dark"]) {
    await page.locator("html").evaluate((root, theme) => { root.dataset.appTheme = theme; }, theme);
    const panel = page.locator(".ctx-row__body");
    expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await panel.screenshot({ path: test.info().outputPath("context-" + theme + ".png") });
  }
});
