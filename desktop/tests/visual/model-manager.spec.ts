import { expect, test } from "@playwright/test";

const fixtureUrl = "/tests/visual/fixtures/model-manager.html";

test("思考强度可以测试、保存、回显并恢复默认", async ({ page }) => {
  await openModelManager(page);
  await page.getByRole("button", { name: "编辑 自定义模型" }).click();
  const effort = page.getByLabel("思考强度", { exact: true });
  await expect(effort).toHaveValue("0");
  await effort.press("ArrowRight");
  await effort.press("ArrowRight");
  await effort.press("ArrowRight");
  await page.getByRole("button", { name: "测试连接", exact: true }).click();
  await expect(page.getByText("连接成功 · 12 ms", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.locator(".current-model-id")).toContainText("高 · 深入思考");
  await page.getByRole("button", { name: "编辑 自定义模型" }).click();
  await expect(effort).toHaveValue("3");
  await effort.press("Home");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await page.getByRole("button", { name: "编辑 自定义模型" }).click();
  await expect(effort).toHaveValue("0");
  const calls = await page.evaluate(() => {
    const api = (window as unknown as { __modelManagerFixture: { saveCalls: Record<string, unknown>[]; testCalls: Record<string, unknown>[] } }).__modelManagerFixture;
    return { saves: api.saveCalls.map(call => call.reasoning_effort), tests: api.testCalls.map(call => call.reasoning_effort) };
  });
  expect(calls).toEqual({ saves: ["high", ""], tests: ["high"] });
});

type FixtureApi = {
  deleteCalls: string[];
  setDeleteMode: (mode: "success" | "error") => void;
  setDeleteDelay: (delay: number) => void;
  setSelectDelay: (delay: number) => void;
};
type FixtureSnapshot = Pick<FixtureApi, "deleteCalls">;

async function openModelManager(page: import("@playwright/test").Page): Promise<void> {
  await page.setViewportSize({ width: 980, height: 720 });
  await page.goto(fixtureUrl, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("自定义模型", { exact: true })).toBeVisible();
}

async function fixtureApi(page: import("@playwright/test").Page): Promise<FixtureSnapshot> {
  return await page.evaluate(() => {
    const value = (window as unknown as { __modelManagerFixture: FixtureApi }).__modelManagerFixture;
    return { deleteCalls: [...value.deleteCalls] };
  });
}

async function setDeleteMode(page: import("@playwright/test").Page, mode: "success" | "error"): Promise<void> {
  await page.evaluate((nextMode) => {
    (window as unknown as { __modelManagerFixture: FixtureApi }).__modelManagerFixture.setDeleteMode(nextMode);
  }, mode);
}

test("取消模型删除确认不会调用删除 API", async ({ page }) => {
  await openModelManager(page);

  await page.getByRole("button", { name: "删除 自定义模型" }).click();
  const dialog = page.getByRole("alertdialog", { name: "删除模型" });
  await expect(dialog).toContainText("自定义模型");
  await expect(dialog.getByRole("button", { name: "取消", exact: true })).toBeFocused();
  await dialog.getByRole("button", { name: "取消", exact: true }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByText("自定义模型", { exact: true })).toBeVisible();
  expect((await fixtureApi(page)).deleteCalls).toEqual([]);
});

test("确认删除成功后只调用一次并移除模型", async ({ page }) => {
  await openModelManager(page);
  await page.evaluate(() => {
    (window as unknown as { __modelManagerFixture: FixtureApi }).__modelManagerFixture.setDeleteDelay(180);
  });

  await page.getByRole("button", { name: "删除 自定义模型" }).click();
  const dialog = page.getByRole("alertdialog", { name: "删除模型" });
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "删除中", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "删除 自定义模型" })).toBeDisabled();
  await dialog.getByRole("button", { name: "删除中", exact: true }).evaluate((button) => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });

  await expect(dialog).toBeHidden();
  await expect(page.getByText("自定义模型", { exact: true })).toHaveCount(0);
  await expect(page.getByText("服务端返回模型", { exact: true })).toBeVisible();
  expect((await fixtureApi(page)).deleteCalls).toEqual(["custom"]);
});

test("删除失败保留模型并允许重新发起", async ({ page }) => {
  await openModelManager(page);
  await setDeleteMode(page, "error");

  await page.getByRole("button", { name: "删除 自定义模型" }).click();
  await page.getByRole("alertdialog", { name: "删除模型" }).getByRole("button", { name: "确认删除", exact: true }).click();

  await expect(page.getByRole("alertdialog", { name: "删除模型" })).toBeHidden();
  await expect(page.getByText("删除模型失败：本地服务暂时不可用", { exact: false })).toBeVisible();
  await expect(page.getByText("自定义模型", { exact: true })).toBeVisible();
  expect((await fixtureApi(page)).deleteCalls).toEqual(["custom"]);

  await setDeleteMode(page, "success");
  await page.getByRole("button", { name: "删除 自定义模型" }).click();
  await page.getByRole("alertdialog", { name: "删除模型" }).getByRole("button", { name: "确认删除", exact: true }).click();

  await expect(page.getByText("自定义模型", { exact: true })).toHaveCount(0);
  await expect(page.getByText("删除模型失败：本地服务暂时不可用", { exact: false })).toHaveCount(0);
  expect((await fixtureApi(page)).deleteCalls).toEqual(["custom", "custom"]);
});

test("删除成功后不会被过期的模型切换响应覆盖", async ({ page }) => {
  await openModelManager(page);
  await page.evaluate(() => {
    (window as unknown as { __modelManagerFixture: FixtureApi }).__modelManagerFixture.setSelectDelay(220);
  });

  await page.getByRole("button", { name: "将 自定义模型 设为当前模型" }).click();
  await page.getByRole("button", { name: "删除 自定义模型" }).click();
  await page.getByRole("alertdialog", { name: "删除模型" }).getByRole("button", { name: "确认删除", exact: true }).click();

  await expect(page.getByText("自定义模型", { exact: true })).toHaveCount(0);
  await page.waitForTimeout(300);
  await expect(page.getByText("自定义模型", { exact: true })).toHaveCount(0);
  expect((await fixtureApi(page)).deleteCalls).toEqual(["custom"]);
});

test("Escape 可以取消模型删除确认", async ({ page }) => {
  await openModelManager(page);

  await page.getByRole("button", { name: "删除 自定义模型" }).click();
  const dialog = page.getByRole("alertdialog", { name: "删除模型" });
  await expect(dialog.getByRole("button", { name: "取消", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");

  await expect(dialog).toBeHidden();
  expect((await fixtureApi(page)).deleteCalls).toEqual([]);
});

test("当前模型和内置模型没有删除操作", async ({ page }) => {
  await openModelManager(page);

  await expect(page.getByRole("button", { name: "删除 当前模型" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "删除 内置模型" })).toHaveCount(0);
  await expect(page.getByText("内置", { exact: true })).toBeVisible();
});
