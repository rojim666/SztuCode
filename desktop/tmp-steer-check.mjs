import { chromium } from "playwright-core";

const base = ["http", "//127.0.0.1:1424/"].join(":");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1180, height: 820 } });
const messages = [];
page.on("console", (message) => {
  if (message.type() === "warning" || message.type() === "error") messages.push(`${message.type()}: ${message.text()}`);
});
page.on("pageerror", (error) => messages.push(`pageerror: ${error.message}`));
try {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  const steeringText = "追加：顺便把回归测试也补上";
  const dump = await page.locator("#app").evaluate(async (root, content) => {
    const state = root.__vue_app__?._instance?.setupState;
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
    // 真实时序：用户消息步 → run.started → step.started → token → 追加指令 → token → 下一次 step.started
    state.timeline = new Map([[1, {
      step: 1, status: "thinking", tokens: [], toolCalls: [], runId,
      userMessage: "先实现登录校验", userMessageTime: stamp, runStartedAt: stamp,
    }]]);
    state.activeRunId = runId;
    state.runActive = true;
    state.applyRuntimeEvent({ type: "run.started", run_id: runId, ts: stamp });
    state.applyRuntimeEvent({ type: "step.started", run_id: runId, step: 1, ts: stamp });
    state.applyRuntimeEvent({ type: "llm.token", run_id: runId, step: 1, token: "PRE_STEER_TOKEN" });
    state.applyRuntimeEvent({ type: "session.message_steered", session_id: "session-steering", run_id: runId, content, ts: stamp });
    state.applyRuntimeEvent({ type: "llm.token", run_id: runId, step: 1, token: "POST_STEER_TOKEN" });
    state.applyRuntimeEvent({ type: "step.started", run_id: runId, step: 2, ts: stamp });
    state.applyRuntimeEvent({ type: "llm.token", run_id: runId, step: 2, token: "STEP2_TOKEN" });
    state.applyRuntimeEvent({ type: "step.started", run_id: runId, step: 3, ts: stamp });
    state.applyRuntimeEvent({ type: "llm.token", run_id: runId, step: 3, token: "STEP3_TOKEN" });
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await Promise.resolve();
    return [...state.timeline.values()].sort((a, b) => a.step - b.step).map((step) => ({
      step: step.step, status: step.status, runId: step.runId,
      userMessage: step.userMessage ?? null,
      streamText: step.streamText ?? null,
      tokens: step.tokens.join(""),
      injections: (step.contextInjections ?? []).map((entry) => entry.source),
    }));
  }, steeringText);
  await page.waitForTimeout(800);
  const observed = await page.evaluate(() => ({
    turns: [...document.querySelectorAll(".execution-timeline > .timeline-step")].map((node) => node.textContent.trim().slice(0, 120)),
    userMessages: [...document.querySelectorAll(".timeline-user-message")].map((node) => node.textContent.trim()),
    stopVisible: Boolean([...document.querySelectorAll("button")].find((b) => (b.getAttribute("aria-label") ?? "") === "停止任务")),
  }));
  console.log(JSON.stringify({ dump, observed, messages }, null, 2));
} finally {
  await browser.close();
}
