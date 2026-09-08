import { expect, test } from "@playwright/test";

test("automation tasks can be created, paused, edited, filtered and deleted", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await page.goto("/");
  await page.evaluate(async () => {
    const { IpcClient } = await import("/src/lib/ipc.ts");
    const entries: Record<string, any>[] = [];
    IpcClient.prototype.connect = async () => undefined;
    IpcClient.prototype.request = async (method: string, params: Record<string, any> = {}) => {
      if (method === "schedule.list") return { tasks: structuredClone(entries) };
      if (method === "schedule.create") {
        const task = { ...params, id: "automation-1", updated_at: new Date().toISOString() };
        entries.push(task); return { task: structuredClone(task) };
      }
      if (method === "schedule.update") {
        const index = entries.findIndex((item) => item.id === params.id);
        entries[index] = { ...params, updated_at: new Date().toISOString() };
        return { task: structuredClone(entries[index]) };
      }
      if (method === "schedule.pause") {
        const task = entries.find((item) => item.id === params.id)!; task.status = "paused";
        return { task: structuredClone(task) };
      }
      if (method === "schedule.run") return { task: structuredClone(entries.find((item) => item.id === params.id)), accepted: true };
      if (method === "schedule.delete") {
        const index = entries.findIndex((item) => item.id === params.id); entries.splice(index, 1);
        return { id: params.id, deleted: true };
      }
      return {};
    };
    const root = document.querySelector("#app") as HTMLElement & { __vue_app__?: { unmount(): void } };
    root.__vue_app__?.unmount(); root.style.height = "100vh";
    const { createApp } = await import("/node_modules/.vite/deps/vue.js");
    const { default: AutomationPage } = await import("/src/components/Automation/AutomationPage.vue");
    const { i18n } = await import("/src/i18n/index.ts");
    createApp(AutomationPage, { connected: true, workspaceId: "workspace-1" }).use(i18n).mount(root);
  });

  await expect(page.getByText("暂无自动化任务")).toBeVisible();
  await page.getByRole("button", { name: "新建任务" }).click();
  await page.getByLabel("名称").fill("每周项目复盘");
  await page.getByLabel("执行内容").fill("总结本周代码变更、测试结果和下周风险。只在有实质进展时输出。");
  await page.getByRole("button", { name: "每周" }).click();
  await page.getByLabel("星期").selectOption("3");
  await page.getByLabel("时间").fill("18:30");
  await page.getByRole("button", { name: "创建任务" }).click();

  const card = page.locator(".automation-card");
  await expect(card).toHaveCount(1);
  await expect(card).toContainText("每周项目复盘");
  await expect(card).toContainText("每周三 18:30");
  await card.getByTitle("立即运行").click();
  await expect(page.getByRole("status")).toContainText("已提交“每周项目复盘”");
  await card.getByRole("button", { name: "暂停任务" }).click();
  await expect(card).toContainText("已暂停");
  await page.getByRole("button", { name: "已暂停", exact: true }).click();
  await expect(card).toBeVisible();

  await card.getByTitle("编辑").click();
  await page.getByLabel("名称").fill("项目周报");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(card).toContainText("项目周报");

  page.once("dialog", (dialog) => dialog.accept());
  await card.getByTitle("删除").click();
  await expect(page.getByText("暂无自动化任务")).toBeVisible();
});
