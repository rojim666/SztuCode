import { expect, test } from "@playwright/test";

test("temporary tasks remain projectless across refresh, first send and follow-up", async ({ page }) => {
  // The browser harness has no Tauri process launcher; RPC calls are mocked below.
  await page.route("**/src/services/sztu-runtime.ts", async route => {
    const response = await route.fetch();
    const body = (await response.text()).replace(/await invoke\(["']daemon_start["']\);/, "");
    await route.fulfill({ response, body });
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const result = await page.locator("#app").evaluate(async root => {
    const moduleUrl = "/src/lib/ipc.ts";
    const { IpcClient } = await import(moduleUrl);
    const requests: Array<{ method: string; params: Record<string, unknown> }> = [];
    const project = { workspace_id: "other-project", name: "Other project", path: "F:/other", archived: false };
    const sessions = [{ session_id: "other-session", workspace_id: "other-project" as string | null, title: "Other", archived: false, status: "waiting_for_input" }];
    IpcClient.prototype.connect = async () => {};
    IpcClient.prototype.request = async (method: string, params: Record<string, unknown> = {}) => {
      requests.push({ method, params });
      switch (method) {
        case "workspace.list": return { workspaces: [project] };
        case "session.list": return { sessions: [...sessions] };
        case "session.create":
          sessions.push({ session_id: "temporary-session", workspace_id: params.workspace_id as string ?? null, title: "Temporary", archived: false, status: "waiting_for_input" });
          return { session_id: "temporary-session" };
        case "session.send_message": return { run_id: "run-" + requests.length };
        case "session.get_history": return { messages: [] };
        case "provider.status": return { models: [], mcp_servers: [] };
        default: return {};
      }
    };
    const state = (root as HTMLElement & { __vue_app__: { _instance: { setupState: Record<string, any> } } }).__vue_app__._instance.setupState;
    await state.refreshIndex(false);
    state.beginTask(project);
    state.clearLauncherWorkspace();
    await state.refreshIndex(false);
    const afterRefresh = { activeId: state.activeId, workspace: state.workspace, activeWorkspace: state.activeWorkspace };
    const sent = await state.submitTask("hello", "hello");
    await state.refreshIndex(false);
    const afterSend = { activeId: state.activeId, workspace: state.workspace, activeWorkspace: state.activeWorkspace };
    await state.chooseTask("other-session");
    state.setInspectorOpen(true);
    await new Promise(requestAnimationFrame);
    await state.chooseTask("temporary-session");
    await state.refreshIndex(false);
    const reopened = { activeId: state.activeId, workspace: state.workspace, activeWorkspace: state.activeWorkspace };
    const followup = await state.startSessionRun("temporary-session", "continue", "continue");
    state.toggleInspector();
    await new Promise(requestAnimationFrame);
    return { afterRefresh, afterSend, reopened, sent, followup, inspectorOpen: state.inspectorOpen, requests: requests.filter(r => r.method === "session.create" || r.method === "session.send_message") };
  });
  expect(result.afterRefresh).toEqual({ activeId: null, workspace: null, activeWorkspace: null });
  expect(result.sent).toBe(true);
  expect(result.followup).toBe(true);
  expect(result.afterSend).toEqual({ activeId: "temporary-session", workspace: null, activeWorkspace: null });
  expect(result.reopened).toEqual(result.afterSend);
  expect(result.inspectorOpen).toBe(false);
  await expect(page.locator('.work-header .temporary-task-label')).toHaveText('临时任务');
  await expect(page.locator('.work-header .workspace-trigger')).toHaveCount(0);
  await expect(page.locator('.workspace-panel-toggle')).toHaveCount(0);
  await expect(page.locator('.work-header .source-control-toggle')).toHaveCount(0);
  await expect(page.locator('.layout-divider')).toHaveCount(0);
  expect(result.requests.filter(r => r.method === "session.create")).toHaveLength(1);
  expect(result.requests[0].params.workspace_id).toBeUndefined();
  expect(result.requests.filter(r => r.method === "session.send_message").map(r => r.params.session_id)).toEqual(["temporary-session", "temporary-session"]);
});
