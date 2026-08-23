import { expect, test } from "@playwright/test";

type DiffState = {
  changes?: Array<{ path: string; index_status: string; worktree_status: string; additions: number; deletions: number }>;
  selected?: string;
  diff?: string;
  loadingChanges?: boolean;
  loadingDiff?: boolean;
  changesError?: string;
  diffError?: string;
  actionError?: string;
};

/** 通过 DOM 元素上的 __vueParentComponent 拿到 DiffReview 实例并注入状态 */
async function openDiffFixture(
  page: import("@playwright/test").Page,
  state: DiffState = {},
  viewport = { width: 1280, height: 800 },
): Promise<() => Record<string, unknown>> {
  await page.setViewportSize(viewport);
  await page.goto("/tests/visual/fixtures/diff-review.html");

  await page.locator(".diff-review").evaluate((el, extra) => {
    const instance = (el as HTMLElement & { __vueParentComponent?: { setupState?: Record<string, unknown> } }).__vueParentComponent;
    const setup = instance?.setupState;
    if (!setup) throw new Error("DiffReview setupState is unavailable");
    const apply = (key: string, value: unknown) => {
      const refish = setup[key] as { value?: unknown } | undefined;
      if (refish && typeof refish === "object" && "value" in refish) refish.value = value;
      else setup[key] = value;
    };
    for (const [key, value] of Object.entries(extra as DiffState)) {
      if (value === undefined) continue;
      apply(key, value);
    }
  }, state);

  return () => page.locator(".diff-review").evaluate((el) => {
    const instance = (el as HTMLElement & { __vueParentComponent?: { setupState?: Record<string, unknown> } }).__vueParentComponent;
    return instance?.setupState ?? {};
  });
}

const visualChanges = [
  {
    path: "src/features/diff-review/components/very-long-change-path-that-must-not-push-actions-out-of-the-container.ts",
    index_status: "M",
    worktree_status: "M",
    additions: 24,
    deletions: 9,
  },
  { path: "src/services/runtime.ts", index_status: "M", worktree_status: "M", additions: 3, deletions: 1 },
];

const visualDiff = [
  "--- a/src/features/diff-review/components/very-long-change-path-that-must-not-push-actions-out-of-the-container.ts",
  "+++ b/src/features/diff-review/components/very-long-change-path-that-must-not-push-actions-out-of-the-container.ts",
  "@@ -1,3 +1,4 @@",
  `+export const responsiveDiffReview = '${"independently-scrollable-diff-line-".repeat(10)}';`,
].join("\n");

test("1280px keeps a two-column review layout", async ({ page }) => {
  await openDiffFixture(page, {
    changes: visualChanges,
    selected: visualChanges[0].path,
    diff: visualDiff,
  });

  await expect(page.locator(".diff-review__pre")).toContainText("independently-scrollable-diff-line-independently-scrollable-diff-line");
  const layout = await page.evaluate(() => {
    const files = document.querySelector<HTMLElement>(".diff-review__files")!;
    const view = document.querySelector<HTMLElement>(".diff-review__view")!;
    return {
      filesRight: files.getBoundingClientRect().right,
      filesWidth: files.getBoundingClientRect().width,
      viewLeft: view.getBoundingClientRect().left,
    };
  });

  expect(layout.filesRight).toBeLessThanOrEqual(layout.viewLeft);
  expect(layout.filesWidth).toBe(320);
  await expect(page).toHaveScreenshot("diff-review-1280.png");
});

test("760px keeps review controls in stacked panels", async ({ page }) => {
  await openDiffFixture(page, {
    changes: visualChanges,
    selected: visualChanges[0].path,
    diff: visualDiff,
  }, { width: 760, height: 800 });

  const filePath = page.locator(".diff-review__file-path").first();
  const acceptFile = page.locator(".diff-review__file-accept").first();
  const rejectFile = page.locator(".diff-review__file-reject").first();
  const acceptAll = page.getByRole("button", { name: "全部接受" });
  const rejectAll = page.getByRole("button", { name: "全部拒绝" });
  await expect(filePath).toBeVisible();
  await expect(acceptFile).toBeVisible();
  await expect(rejectFile).toBeVisible();
  await expect(acceptAll).toBeVisible();
  await expect(rejectAll).toBeVisible();
  await filePath.click({ trial: true });
  await acceptFile.click({ trial: true });
  await rejectFile.click({ trial: true });
  await acceptAll.click({ trial: true });
  await rejectAll.click({ trial: true });
  await expect(page.locator(".diff-review__pre")).toContainText("responsiveDiffReview");

  const layout = await page.evaluate(() => {
    const files = document.querySelector<HTMLElement>(".diff-review__files")!;
    const view = document.querySelector<HTMLElement>(".diff-review__view")!;
    const pre = document.querySelector<HTMLElement>(".diff-review__pre")!;
    return {
      filesBottom: files.getBoundingClientRect().bottom,
      viewTop: view.getBoundingClientRect().top,
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      viewOverflowX: getComputedStyle(view).overflowX,
      viewScrollWidth: view.scrollWidth,
      viewClientWidth: view.clientWidth,
      preFont: getComputedStyle(pre).fontFamily,
    };
  });

  expect(layout.filesBottom).toBeLessThanOrEqual(layout.viewTop);
  expect(layout.pageWidth).toBeLessThanOrEqual(layout.viewportWidth);
  expect(layout.viewOverflowX).toBe("auto");
  expect(layout.viewScrollWidth).toBeGreaterThan(layout.viewClientWidth);
  expect(layout.preFont).toContain("Consolas");
  await expect(page).toHaveScreenshot("diff-review-760.png");
});

test("列表加载失败时展示内联错误与重试入口", async ({ page }) => {
  await openDiffFixture(page, { changes: [], selected: "", changesError: "本地服务尚未连接" });

  await expect(page.getByText(/加载失败/)).toBeVisible();
  await expect(page.getByRole("button", { name: /重试/ })).toBeVisible();
  await expect(page.getByText("选择左侧文件查看差异")).toBeVisible();
});

test("Diff 加载失败时保留选中文件并展示重试", async ({ page }) => {
  const readState = await openDiffFixture(page, {
    changes: [
      { path: "src/a.py", index_status: "M", worktree_status: "M", additions: 2, deletions: 1 },
      { path: "src/b.py", index_status: "M", worktree_status: "M", additions: 5, deletions: 3 },
    ],
    selected: "src/a.py",
    diffError: "本地服务尚未连接",
  });

  await expect(page.getByText(/差异加载失败/)).toBeVisible();
  await expect(page.getByRole("button", { name: /重试/ })).toBeVisible();
  await expect(page.locator(".diff-review__file.active")).toContainText("src/a.py");

  const state = await readState();
  expect(state.diff).toBe("");
  expect(state.selected).toBe("src/a.py");
});

test("Diff 加载成功时展示差异内容", async ({ page }) => {
  await openDiffFixture(page, {
    changes: [
      { path: "src/a.py", index_status: "M", worktree_status: "M", additions: 2, deletions: 1 },
    ],
    selected: "src/a.py",
    diff: "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,3 +1,4 @@\n+print('hello')",
  });

  await expect(page.locator(".diff-review__pre")).toContainText("print('hello')");
  await expect(page.getByText(/差异加载失败/)).toHaveCount(0);
});

test("接受失败时不标记已暂存并展示内联错误", async ({ page }) => {
  await openDiffFixture(page, {
    changes: [
      { path: "src/a.py", index_status: "M", worktree_status: "M", additions: 2, deletions: 1 },
    ],
    selected: "src/a.py",
    diff: "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1,2 @@\n+print('x')",
  });

  await page.locator(".diff-review__file-accept").click();
  // 无 daemon：stageChanges reject → 展示接受失败，且不标记已暂存
  await expect(page.getByText(/接受失败/)).toBeVisible();
  await expect(page.getByText("已暂存")).toHaveCount(0);
});

test("拒绝失败时不标记已拒绝并展示内联错误", async ({ page }) => {
  await openDiffFixture(page, {
    changes: [
      { path: "src/a.py", index_status: "M", worktree_status: "M", additions: 2, deletions: 1 },
    ],
    selected: "src/a.py",
    diff: "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1,2 @@\n+print('x')",
  });

  page.on("dialog", (dialog) => void dialog.accept());
  await page.locator(".diff-review__file-reject").click();
  await expect(page.getByText(/拒绝失败/)).toBeVisible();
  await expect(page.getByText("已拒绝")).toHaveCount(0);
});

test("窄窗口中空/错误/成功状态不重叠", async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 600 });
  await page.goto("/tests/visual/fixtures/diff-review.html");

  // 统一通过 .diff-review 元素上的 __vueParentComponent 注入/读取状态
  const injectState = (state: DiffState) => page.locator(".diff-review").evaluate((el, extra) => {
    const instance = (el as HTMLElement & { __vueParentComponent?: { setupState?: Record<string, unknown> } }).__vueParentComponent;
    const setup = instance?.setupState;
    if (!setup) throw new Error("DiffReview setupState is unavailable");
    const apply = (key: string, value: unknown) => {
      const refish = setup[key] as { value?: unknown } | undefined;
      if (refish && typeof refish === "object" && "value" in refish) refish.value = value;
      else setup[key] = value;
    };
    for (const [key, value] of Object.entries(extra as DiffState)) {
      if (value === undefined) continue;
      apply(key, value);
    }
  }, state);

  // 1) 空状态：无文件时提示与视图占位不重叠
  await injectState({ changes: [], selected: "", changesError: "" });
  await expect(page.getByText("暂无待审文件")).toBeVisible();
  await expect(page.getByText("选择左侧文件查看差异")).toBeVisible();

  // 2) 错误状态：列表加载失败 + diff 加载失败同时展示，且不重叠
  await injectState({
    changes: [
      { path: "src/a.py", index_status: "M", worktree_status: "M", additions: 2, deletions: 1 },
    ],
    selected: "src/a.py",
    changesError: "",
    diffError: "本地服务尚未连接",
  });
  await expect(page.getByText(/差异加载失败/)).toBeVisible();

  const errorGeometry = await page.evaluate(() => {
    const fileList = document.querySelector<HTMLElement>(".diff-review__files")!;
    const view = document.querySelector<HTMLElement>(".diff-review__view")!;
    const error = document.querySelector<HTMLElement>(".diff-review__error")!;
    return {
      // 窄窗口中文件列表位于 Diff 视图上方，两个区域不互相覆盖
      filesBottom: fileList.getBoundingClientRect().bottom,
      viewTop: view.getBoundingClientRect().top,
      errorInsideView: error.getBoundingClientRect().left >= view.getBoundingClientRect().left,
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    };
  });
  expect(errorGeometry.filesBottom).toBeLessThanOrEqual(errorGeometry.viewTop);
  expect(errorGeometry.errorInsideView).toBe(true);
  expect(errorGeometry.pageWidth).toBeLessThanOrEqual(errorGeometry.viewportWidth);

  // 3) 成功状态：diff 内容与内联错误不重叠
  await injectState({
    diffError: "",
    diff: "--- a/src/a.py\n+++ b/src/a.py\n@@ -1,3 +1,4 @@\n+print('hello')",
  });
  await expect(page.locator(".diff-review__pre")).toBeVisible();

  const successGeometry = await page.evaluate(() => {
    const pre = document.querySelector<HTMLElement>(".diff-review__pre")!;
    const inline = document.querySelector<HTMLElement>(".diff-review__inline-error");
    const preRect = pre.getBoundingClientRect();
    const inlineRect = inline ? inline.getBoundingClientRect() : null;
    return {
      // 窄窗口下 diff 内容可见且不被顶栏遮挡
      preTop: preRect.top,
      headerBottom: document.querySelector<HTMLElement>(".diff-review__top")!.getBoundingClientRect().bottom,
      inlineOverlap: inlineRect ? inlineRect.bottom > preRect.top : false,
    };
  });
  expect(successGeometry.preTop).toBeGreaterThanOrEqual(successGeometry.headerBottom);
  expect(successGeometry.inlineOverlap).toBe(false);
});
