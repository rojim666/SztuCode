import { expect, test } from "@playwright/test";

// 追加指令（steer）在 run 运行中发送时：命令本身要作为用户消息可见，
// 并把本轮隔断成新的一轮；run 继续执行，不取消也不重开。
test("steering command shows as a user message and splits the running turn", async ({ page }) => {
  await page.setViewportSize({ width: 1180, height: 820 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const warnings: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "warning" || message.type() === "error") warnings.push(message.text());
  });

  const steeringText = "追加：顺便把回归测试也补上";
  await page.locator("#app").evaluate((root, content) => {
    const app = (root as HTMLElement & { __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } } }).__vue_app__;
    const state = app?._instance?.setupState as {
      timeline: Map<number, unknown>;
      workspace: Record<string, unknown> | null;
      workspaces: Array<Record<string, unknown>>;
      sessions: Array<Record<string, unknown>>;
      activeId: string | null;
      activeRunId: string | null;
      runActive: boolean;
      applyRuntimeEvent: (event: Record<string, unknown>) => void;
    } | undefined;
    if (!state) throw new Error("Vue application state is unavailable");

    const runId = "run-steering";
    const stamp = new Date().toISOString();
    const workspace = { workspace_id: "workspace-steering", name: "Steering", path: "F:/steering", archived: false };
    state.workspace = workspace;
    state.workspaces = [workspace];
    state.sessions = [{
      session_id: "session-steering", title: "追加指令", status: "active", updated_at: "",
      archived: false, pinned: false, workspace_id: "workspace-steering",
      total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0,
    }];
    state.activeId = "session-steering";
    state.timeline = new Map([[1, {
      step: 1, status: "thinking", tokens: [], toolCalls: [], runId,
      userMessage: "先实现登录校验", userMessageTime: stamp, runStartedAt: stamp,
    }]]);
    state.activeRunId = runId;
    state.runActive = true;
    // 真实事件顺序：run 已跑到第 1 步，用户此时发送追加指令，run 继续到后续步骤
    state.applyRuntimeEvent({ type: "run.started", run_id: runId, ts: stamp });
    state.applyRuntimeEvent({ type: "step.started", run_id: runId, step: 1, ts: stamp });
    state.applyRuntimeEvent({ type: "llm.token", run_id: runId, step: 1, token: "PRE_STEER_TOKEN" });
    state.applyRuntimeEvent({ type: "session.message_steered", session_id: "session-steering", run_id: runId, content, ts: stamp });
    state.applyRuntimeEvent({ type: "llm.token", run_id: runId, step: 1, token: "POST_STEER_TOKEN" });
    state.applyRuntimeEvent({ type: "step.started", run_id: runId, step: 2, ts: stamp });
    state.applyRuntimeEvent({ type: "llm.token", run_id: runId, step: 2, token: "STEP2_TOKEN" });
  }, steeringText);

  // 同一个 run 被隔断成两轮：追加指令自己开启新一轮
  const turns = page.locator(".execution-timeline > .timeline-step");
  await expect(turns).toHaveCount(2);
  await expect(turns.first().locator(".timeline-user-message")).toContainText("先实现登录校验");
  await expect(turns.nth(1).locator(".timeline-user-message")).toContainText(steeringText);
  // 追加前的输出留在原轮次，追加后的输出落在隔断之后
  await expect(turns.first()).toContainText("PRE_STEER_TOKEN");
  await expect(turns.first()).not.toContainText("POST_STEER_TOKEN");
  await expect(turns.nth(1)).toContainText("POST_STEER_TOKEN");
  await expect(turns.nth(1)).toContainText("STEP2_TOKEN");
  // 运行未被中断：停止入口仍在，输入框保持追加模式
  await expect(page.getByRole("button", { name: "停止任务" })).toBeVisible();
  // 同一 run 的两轮不能重名，否则 Vue 会复用错误的节点
  expect(warnings.filter((text) => /duplicate keys/i.test(text))).toEqual([]);
});
