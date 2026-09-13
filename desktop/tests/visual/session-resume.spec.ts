import { expect, test } from "@playwright/test";

// 全部任务页对已归档 / 已完成（closed）任务提供「恢复任务」入口：
// 后端 session.resume 会取消归档，并把 chat 会话重新置为可继续输入。
test("board restore button resumes archived and completed tasks", async ({ page }) => {
  // 浏览器测试环境没有 Tauri 进程，daemon_start 调用需要从服务模块里移除。
  await page.route("**/src/services/sztu-runtime.ts", async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace(/await invoke\(["']daemon_start["']\);/, "");
    await route.fulfill({ response, body });
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("#app").evaluate(async root => {
    const moduleUrl = "/src/lib/ipc.ts";
    const { IpcClient } = await import(moduleUrl);
    const requests: Array<{ method: string; params: Record<string, unknown> }> = [];
    const sessions = [
      { session_id: "archived-task", title: "Archived candidate", archived: true, pinned: false, status: "closed", updated_at: "2026-09-13T00:00:00.000Z" },
      { session_id: "closed-task", title: "Closed candidate", archived: false, pinned: false, status: "closed", updated_at: "2026-09-13T00:00:00.000Z" },
      { session_id: "live-task", title: "Live candidate", archived: false, pinned: false, status: "waiting_for_input", updated_at: "2026-09-13T00:00:00.000Z" },
    ];
    IpcClient.prototype.connect = async () => {};
    IpcClient.prototype.request = async (method: string, params: Record<string, unknown> = {}) => {
      requests.push({ method, params });
      switch (method) {
        case "workspace.list": return { workspaces: [] };
        case "session.list": return { sessions: sessions.map((item) => ({ ...item })) };
        case "session.resume": {
          const target = sessions.find((item) => item.session_id === params.session_id);
          if (target) { target.archived = false; target.status = "waiting_for_input"; }
          return { session: { ...target } };
        }
        case "provider.status": return { models: [], mcp_servers: [] };
        default: return {};
      }
    };
    (window as Window & { __resumeRequests?: typeof requests }).__resumeRequests = requests;
    const state = (root as HTMLElement & { __vue_app__: { _instance: { setupState: Record<string, any> } } }).__vue_app__._instance.setupState;
    await state.refreshIndex(false);
    state.openPage("board");
  });

  const board = page.locator(".board-page .session-board");
  const archivedRow = board.locator("article.archived");
  const closedRow = board.locator("article").filter({ hasText: "Closed candidate" });
  const liveRow = board.locator("article").filter({ hasText: "Live candidate" });

  // 三类状态：已归档 → 只有「恢复任务」；已完成 → 归档 + 恢复；等待输入 → 只有归档。
  await expect(archivedRow).toHaveCount(1);
  await expect(archivedRow.getByRole("button", { name: "恢复任务" })).toHaveCount(1);
  await expect(archivedRow.getByRole("button", { name: "归档会话" })).toHaveCount(0);
  await expect(closedRow.getByRole("button", { name: "恢复任务" })).toHaveCount(1);
  await expect(closedRow.getByRole("button", { name: "归档会话" })).toHaveCount(1);
  await expect(liveRow.getByRole("button", { name: "恢复任务" })).toHaveCount(0);

  await archivedRow.getByRole("button", { name: "恢复任务" }).click();
  // 恢复后该任务离开「已归档」分组，并重新出现在进行中列表。
  await expect(board.locator("article.archived")).toHaveCount(0);
  await expect(board.locator("article").filter({ hasText: "Archived candidate" })).toHaveCount(1);
  await expect(closedRow.getByRole("button", { name: "恢复任务" })).toHaveCount(1);

  await closedRow.getByRole("button", { name: "恢复任务" }).click();
  // 状态回到等待输入后，恢复入口随之消失，避免重复恢复。
  await expect(closedRow.getByRole("button", { name: "恢复任务" })).toHaveCount(0);

  const resumed = await page.evaluate(() => ((window as Window & { __resumeRequests?: Array<{ method: string; params: { session_id?: string } }> }).__resumeRequests ?? [])
    .filter((item) => item.method === "session.resume")
    .map((item) => item.params.session_id));
  expect(resumed).toEqual(["archived-task", "closed-task"]);
});
