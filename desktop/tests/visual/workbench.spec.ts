import { expect, test } from "@playwright/test";

test("application title bar exposes file edit view and help menus", async ({ page }) => {
  await page.setViewportSize({ width: 680, height: 640 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const menuBar = page.getByRole("navigation", { name: "应用菜单" });
  await expect(menuBar.locator(":scope > .app-menu-item > button")).toHaveText(["文件", "编辑", "视图", "帮助"]);

  await page.getByRole("button", { name: "文件", exact: true }).click();
  const fileMenu = page.getByRole("menu", { name: "文件菜单" });
  await expect(fileMenu).toBeVisible();
  await expect(fileMenu.getByRole("menuitem")).toHaveText([/新建任务/, "打开文件夹"]);
  await page.keyboard.press("Escape");
  await expect(fileMenu).toBeHidden();

  await page.getByRole("button", { name: "视图", exact: true }).click();
  await expect(page.getByRole("menu", { name: "视图菜单" })).toBeVisible();
  await page.locator(".task-launcher").click({ position: { x: 10, y: 10 } });
  await expect(page.getByRole("menu", { name: "视图菜单" })).toBeHidden();

  const geometry = await page.evaluate(() => {
    const menu = document.querySelector<HTMLElement>(".app-menu-bar")!.getBoundingClientRect();
    const controls = document.querySelector<HTMLElement>(".window-actions")!.getBoundingClientRect();
    return { menuRight: menu.right, controlsLeft: controls.left };
  });
  expect(geometry.menuRight).toBeLessThan(geometry.controlsLeft);
});

test("agent workbench sidebar prioritizes tasks and project context", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: /新建任务/ })).toBeVisible();
  await page.getByRole("button", { name: "搜索任务或项目", exact: true }).click();
  await expect(page.getByRole("searchbox", { name: "搜索任务或项目" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "工作台工具" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "SztuCode", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "心念为引，一言功毕", exact: true })).toBeVisible();
  await expect(page.locator(".launcher-mark svg")).toBeVisible();
  await expect(page.getByRole("button", { name: "更多", exact: true })).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: "浏览器连接", exact: true })).toBeHidden();
  await page.getByRole("button", { name: "理解项目", exact: true }).click();
  const launcherInput = page.getByPlaceholder("汝之所想，皆以言成");
  await expect(launcherInput).toHaveValue(/分析当前项目结构/);
  await expect(launcherInput).toBeFocused();
  await expect(page.getByRole("button", { name: "理解项目", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page).toHaveScreenshot("task-launcher-v5-1280.png", { fullPage: true });
});

test("new task composer keeps pasted images and attachment control inside the input shell", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const input = page.getByPlaceholder("汝之所想，皆以言成");
  const attachmentButton = page.getByRole("button", { name: "添加附件", exact: true });
  await expect(attachmentButton.locator("svg")).toBeVisible();

  await input.evaluate((textarea) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([
      new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]),
    ], "pasted-image.png", { type: "image/png" }));
    textarea.dispatchEvent(new ClipboardEvent("paste", {
      bubbles: true,
      cancelable: true,
      clipboardData: transfer,
    }));
  });

  const shell = page.locator(".task-launcher .composer-input-shell");
  const strip = shell.locator(".attachment-strip");
  await expect(strip).toBeVisible();
  await expect(strip.locator("img")).toHaveAttribute("alt", "pasted-image.png");

  const geometry = await page.evaluate(() => {
    const shell = document.querySelector<HTMLElement>(".task-launcher .composer-input-shell")!;
    const strip = shell.querySelector<HTMLElement>(".attachment-strip")!;
    const textarea = shell.querySelector<HTMLTextAreaElement>("textarea")!;
    const button = shell.querySelector<HTMLButtonElement>(".launcher-attachment-trigger")!;
    const shellBounds = shell.getBoundingClientRect();
    const stripBounds = strip.getBoundingClientRect();
    const textareaBounds = textarea.getBoundingClientRect();
    const buttonBounds = button.getBoundingClientRect();
    const topElement = document.elementFromPoint(
      buttonBounds.left + buttonBounds.width / 2,
      buttonBounds.top + buttonBounds.height / 2,
    );
    return {
      stripInsideTop: stripBounds.top >= shellBounds.top && stripBounds.bottom <= shellBounds.bottom,
      stripAboveTextarea: stripBounds.bottom <= textareaBounds.top,
      buttonInside: buttonBounds.left >= shellBounds.left && buttonBounds.bottom <= shellBounds.bottom,
      buttonReceivesPointer: topElement === button || button.contains(topElement),
    };
  });

  expect(geometry).toEqual({
    stripInsideTop: true,
    stripAboveTextarea: true,
    buttonInside: true,
    buttonReceivesPointer: true,
  });
});

test("launcher model picker opens fully above the composer without being clipped", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.getByRole("button", { name: "配置模型", exact: true }).click();
  const popover = page.getByRole("menu", { name: "选择模型" });
  await expect(popover).toBeVisible();
  await expect(popover.getByText("暂无模型配置")).toBeVisible();
  await expect(popover.getByRole("menuitem", { name: /添加和管理模型/ })).toBeVisible();

  // 弹出层自输入栏向上展开；确保其顶部未被 composer-input-shell 的 overflow 裁掉
  const painted = await page.evaluate(() => {
    const shell = document.querySelector<HTMLElement>(".task-launcher .composer-input-shell")!;
    const pop = document.querySelector<HTMLElement>(".task-launcher .model-picker-popover")!;
    const shellTop = shell.getBoundingClientRect().top;
    const popBounds = pop.getBoundingClientRect();
    const cx = popBounds.left + popBounds.width / 2;
    const atTop = document.elementFromPoint(cx, popBounds.top + 6);
    return {
      opensAboveShell: popBounds.top < shellTop,
      topPaintsPopover: !!(atTop && atTop.closest(".model-picker-popover")),
    };
  });
  expect(painted).toEqual({ opensAboveShell: true, topPaintsPopover: true });
});

test("work page remains mounted while navigating between top-level pages", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const workHost = page.locator(".work-page-host");
  await expect(workHost).toBeVisible();
  await workHost.evaluate((element) => { (element as HTMLElement & { persistentMarker?: string }).persistentMarker = "mounted"; });

  await page.getByRole("button", { name: "全部任务", exact: true }).click();
  await expect(workHost).toBeHidden();
  await expect(page.locator(".kimi-main")).not.toHaveClass(/work-active/);
  expect(await workHost.evaluate((element) => (element as HTMLElement & { persistentMarker?: string }).persistentMarker)).toBe("mounted");

  await page.getByRole("button", { name: /新建任务/ }).first().click();
  await expect(workHost).toBeVisible();
  await expect(page.locator(".kimi-main")).toHaveClass(/work-active/);
  expect(await workHost.evaluate((element) => (element as HTMLElement & { persistentMarker?: string }).persistentMarker)).toBe("mounted");
});

test("running sessions keep rendering and timing while another session is open", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.evaluate(async () => {
    const { IpcClient } = await import("/src/lib/ipc.ts") as {
      IpcClient: { prototype: { request: (method: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>> } };
    };
    const historyLoads: Record<string, number> = {};
    (window as typeof window & { __sessionHistoryLoads?: Record<string, number> }).__sessionHistoryLoads = historyLoads;
    IpcClient.prototype.request = async (method, params = {}) => {
      if (method === "session.get_history") {
        const sessionId = String(params.session_id ?? "");
        historyLoads[sessionId] = (historyLoads[sessionId] ?? 0) + 1;
        const runId = sessionId === "session-a" ? "run-a" : "run-b";
        return {
          messages: [{
            role: "user",
            content: sessionId === "session-a" ? "持续执行 A" : "查看会话 B",
            run_id: runId,
            ts: new Date(Date.now() - 2200).toISOString(),
          }],
          run_stats: {
            [runId]: { input_tokens: 8, output_tokens: 0, cache_read_input_tokens: 0, elapsed_s: 0, context_pct: 0.01 },
          },
          context_injections: [],
        };
      }
      if (method === "workspace.tree") return { nodes: [] };
      if (method === "change.list") return { changes: [] };
      return {};
    };

    const root = document.querySelector("#app") as HTMLElement & {
      __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } };
    };
    const state = root.__vue_app__?._instance?.setupState as {
      workspace: Record<string, unknown> | null;
      workspaces: Array<Record<string, unknown>>;
      sessions: Array<Record<string, unknown>>;
      chooseTask: (id: string) => Promise<void>;
    } | undefined;
    if (!state) throw new Error("Vue application state is unavailable");
    const workspace = { workspace_id: "workspace-cache", name: "Cache", path: "F:/cache", archived: false };
    state.workspace = workspace;
    state.workspaces = [workspace];
    state.sessions = [
      {
        session_id: "session-a", title: "Session A", status: "active", updated_at: "", archived: false, pinned: false,
        workspace_id: "workspace-cache", latest_run_id: "run-a", total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0,
      },
      {
        session_id: "session-b", title: "Session B", status: "waiting_for_input", updated_at: "", archived: false, pinned: false,
        workspace_id: "workspace-cache", latest_run_id: "run-b", total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0,
      },
    ];
    await state.chooseTask("session-a");
  });

  const timeline = page.locator(".execution-timeline");
  await expect(page.getByRole("button", { name: "停止任务" })).toBeVisible();
  await timeline.evaluate((element) => { (element as HTMLElement & { cacheMarker?: string }).cacheMarker = "session-a"; });
  const initialElapsed = Number((await page.locator(".turn-history-toggle span").textContent())?.match(/[\d.]+/)?.[0] ?? 0);

  await page.evaluate(async () => {
    const root = document.querySelector("#app") as HTMLElement & {
      __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } };
    };
    const state = root.__vue_app__?._instance?.setupState as {
      chooseTask: (id: string) => Promise<void>;
      applyRuntimeEvent: (event: Record<string, unknown>) => void;
    };
    if (!state) throw new Error("Vue application state is unavailable");
    await state.chooseTask("session-b");
    state.applyRuntimeEvent({ type: "llm.token", run_id: "run-a", step: 1, token: "后台增量仍在渲染" });
  });
  await page.waitForTimeout(1250);
  await page.evaluate(async () => {
    const root = document.querySelector("#app") as HTMLElement & {
      __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } };
    };
    const chooseTask = root.__vue_app__?._instance?.setupState?.chooseTask as ((id: string) => Promise<void>) | undefined;
    if (!chooseTask) throw new Error("chooseTask is unavailable");
    await chooseTask("session-a");
  });

  await expect(page.getByText("后台增量仍在渲染", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "停止任务" })).toBeVisible();
  expect(await timeline.evaluate((element) => (element as HTMLElement & { cacheMarker?: string }).cacheMarker)).toBe("session-a");
  const restoredElapsed = Number((await page.locator(".turn-history-toggle span").textContent())?.match(/[\d.]+/)?.[0] ?? 0);
  expect(restoredElapsed).toBeGreaterThan(initialElapsed);
  expect(await page.evaluate(() => (window as typeof window & { __sessionHistoryLoads?: Record<string, number> }).__sessionHistoryLoads)).toEqual({
    "session-a": 1,
    "session-b": 1,
  });
});

test("task conversation scrolls against the workspace divider while controls stay visible", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const entries = Array.from(
    { length: 18 },
    (_, index) => `<article style="min-height:100px;padding:18px;border-bottom:1px solid #eee"><b>Task result ${index + 1}</b><p>Implementation and verification details.</p></article>`,
  ).join("");
  await page.locator(".kimi-main").evaluate((main, timeline) => {
    main.innerHTML = `
      <section class="work-page">
        <div class="work-layout">
          <section class="task-canvas">
            <header class="work-header">agent-learning</header>
            <div class="task-conversation">
              <div class="task-stream"><div class="execution-timeline">${timeline}</div></div>
              <form class="kimi-composer"><textarea></textarea><div class="composer-toolbar"><button class="round">+</button><span></span><button class="send">&uarr;</button></div></form>
            </div>
          </section>
          <div class="layout-divider"></div>
          <aside class="project-inspector file-rail">
            <header class="workspace-tab-strip"><nav><button class="active">任务摘要</button></nav></header>
            <main class="task-summary-view">${Array.from({ length: 30 }, (_, index) => `<section class="summary-section"><button class="summary-section-trigger">Task ${index + 1}</button></section>`).join("")}</main>
          </aside>
        </div>
      </section>`;
  }, entries);

  const stream = page.locator(".task-stream");
  await expect.poll(() => stream.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  await stream.evaluate((element) => { element.scrollTop = 900; });

  const geometry = await page.evaluate(() => {
    const layout = document.querySelector<HTMLElement>(".work-layout")!;
    const taskCanvas = document.querySelector<HTMLElement>(".task-canvas")!;
    const stream = document.querySelector<HTMLElement>(".task-stream")!;
    const composer = document.querySelector<HTMLElement>(".kimi-composer")!;
    const divider = document.querySelector<HTMLElement>(".layout-divider")!;
    const inspector = document.querySelector<HTMLElement>(".project-inspector")!;
    const workHeader = document.querySelector<HTMLElement>(".work-header")!;
    const tabStrip = document.querySelector<HTMLElement>(".workspace-tab-strip")!;
    const summary = document.querySelector<HTMLElement>(".task-summary-view")!;
    const canvasBounds = taskCanvas.getBoundingClientRect();
    const inspectorBounds = inspector.getBoundingClientRect();
    return {
      taskCanvasRight: canvasBounds.right,
      dividerLeft: divider.getBoundingClientRect().left,
      panelGap: inspectorBounds.left - canvasBounds.right,
      panelsTopAligned: Math.abs(canvasBounds.top - inspectorBounds.top),
      panelsBottomAligned: Math.abs(canvasBounds.bottom - inspectorBounds.bottom),
      headersTopAligned: Math.abs(workHeader.getBoundingClientRect().top - tabStrip.getBoundingClientRect().top),
      headersBottomAligned: Math.abs(workHeader.getBoundingClientRect().bottom - tabStrip.getBoundingClientRect().bottom),
      conversationBottom: stream.parentElement!.getBoundingClientRect().bottom,
      composerBottom: composer.getBoundingClientRect().bottom,
      layoutOverflow: getComputedStyle(layout).overflowY,
      streamOverflow: getComputedStyle(stream).overflowY,
      summaryScrollable: summary.scrollHeight > summary.clientHeight,
    };
  });

  expect(geometry.taskCanvasRight).toBeCloseTo(geometry.dividerLeft, 0);
  expect(geometry.panelGap).toBeCloseTo(1, 0);
  expect(geometry.panelsTopAligned).toBeLessThanOrEqual(1);
  expect(geometry.panelsBottomAligned).toBeLessThanOrEqual(1);
  expect(geometry.headersTopAligned).toBeLessThanOrEqual(1);
  expect(geometry.headersBottomAligned).toBeLessThanOrEqual(1);
  expect(geometry.layoutOverflow).toBe("hidden");
  expect(geometry.streamOverflow).toBe("auto");
  expect(geometry.composerBottom).toBeLessThanOrEqual(geometry.conversationBottom);
  expect(geometry.summaryScrollable).toBe(true);
});

test("conversation text column uses the wider desktop layout", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".kimi-main").evaluate((main) => {
    main.innerHTML = `
      <section class="work-page">
        <div class="work-layout no-inspector">
          <section class="task-canvas">
            <header class="work-header">agent-learning</header>
            <div class="task-conversation">
              <div class="task-stream">
                <div class="execution-timeline">
                  <article class="timeline-step">
                    <div class="timeline-user-message">${"一段用于验证会话文字展示宽度的长消息。".repeat(30)}</div>
                    <div class="timeline-assistant"><div class="timeline-step__content"><div class="token-stream">回答正文</div></div></div>
                  </article>
                </div>
              </div>
              <form class="kimi-composer"><textarea></textarea></form>
            </div>
          </section>
          <div class="layout-divider"></div>
        </div>
      </section>`;
  });

  const geometry = await page.evaluate(() => {
    const timeline = document.querySelector<HTMLElement>(".execution-timeline")!;
    const message = document.querySelector<HTMLElement>(".timeline-user-message")!;
    return {
      timelineWidth: timeline.getBoundingClientRect().width,
      timelineMaxWidth: getComputedStyle(timeline).maxWidth,
      messageWidth: message.getBoundingClientRect().width,
      messageMaxWidth: getComputedStyle(message).maxWidth,
    };
  });

  expect(geometry.timelineMaxWidth).toBe("860px");
  expect(geometry.timelineWidth).toBeCloseTo(860, 0);
  expect(geometry.messageMaxWidth).toBe("min(82%, 720px)");
  expect(geometry.messageWidth).toBeGreaterThan(640);
});

test("narrow conversation text aligns with the composer edges", async ({ page }) => {
  await page.setViewportSize({ width: 431, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".kimi-main").evaluate((main) => {
    main.innerHTML = `
      <section class="work-page">
        <div class="work-layout no-inspector">
          <section class="task-canvas">
            <header class="work-header">agent-learning</header>
            <div class="task-conversation">
              <div class="task-stream">
                <div class="execution-timeline">
                  <article class="timeline-step">
                    <div class="timeline-user-message">${"窄窗口下保持右侧对齐。".repeat(20)}</div>
                    <div class="timeline-assistant"><div class="timeline-step__content"><div class="token-stream">窄窗口下正文左侧应与输入框对齐。</div></div></div>
                  </article>
                </div>
              </div>
              <form class="kimi-composer"><textarea></textarea></form>
            </div>
          </section>
          <div class="layout-divider"></div>
        </div>
      </section>`;
  });

  const geometry = await page.evaluate(() => {
    const stream = document.querySelector<HTMLElement>(".task-stream")!;
    const message = document.querySelector<HTMLElement>(".timeline-user-message")!;
    const assistantText = document.querySelector<HTMLElement>(".token-stream")!;
    const composer = document.querySelector<HTMLElement>(".kimi-composer")!;
    const streamRect = stream.getBoundingClientRect();
    const messageRect = message.getBoundingClientRect();
    const assistantRect = assistantText.getBoundingClientRect();
    const composerRect = composer.getBoundingClientRect();
    return {
      streamLeftGap: streamRect.left,
      streamRightGap: window.innerWidth - streamRect.right,
      assistantLeft: assistantRect.left,
      composerLeft: composerRect.left,
      messageRight: messageRect.right,
      composerRight: composerRect.right,
    };
  });

  expect(geometry.streamLeftGap).toBeCloseTo(geometry.streamRightGap, 0);
  expect(geometry.assistantLeft).toBeCloseTo(geometry.composerLeft, 0);
  expect(geometry.messageRight).toBeCloseTo(geometry.composerRight, 0);
});

test("running-task append composer keeps the compact conversation dimensions", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".kimi-main").evaluate((main) => {
    main.innerHTML = `
      <section class="work-page">
        <div class="work-layout no-inspector">
          <section class="task-canvas">
            <div class="task-conversation">
              <div class="task-stream"></div>
              <form class="kimi-composer"><textarea rows="3"></textarea></form>
            </div>
          </section>
        </div>
      </section>`;
  });

  const composer = page.locator(".kimi-composer");
  const idle = await composer.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return { width: box.width, height: box.height };
  });
  await composer.evaluate((element) => element.classList.add("append-mode"));
  const running = await composer.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const conversation = element.parentElement!.getBoundingClientRect();
    const textarea = element.querySelector<HTMLTextAreaElement>("textarea")!;
    return {
      width: box.width,
      height: box.height,
      leftGap: box.left - conversation.left,
      rightGap: conversation.right - box.right,
      textareaMinHeight: parseFloat(getComputedStyle(textarea).minHeight),
    };
  });

  expect(running.width).toBeCloseTo(idle.width, 0);
  expect(running.leftGap).toBeCloseTo(running.rightGap, 0);
  expect(running.height).toBeCloseTo(idle.height, 0);
  expect(running.textareaMinHeight).toBe(52);
});

test("task conversation slash menu opens above the composer without clipping", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".kimi-main").evaluate((main) => {
    main.innerHTML = `
      <section class="work-page">
        <div class="work-layout no-inspector">
          <section class="task-canvas">
            <header class="work-header">agent-learning</header>
            <div class="task-conversation">
              <div class="task-stream"></div>
              <form class="kimi-composer">
                <section class="slash-menu" role="listbox" aria-label="斜杠命令与技能">
                  <div class="slash-menu__scroll"><section class="slash-menu__group"><h3>命令</h3><button><span class="slash-menu__icon command"></span><b>/plan</b><span>制定执行计划</span></button></section></div>
                  <footer><span>Enter 调用</span></footer>
                </section>
                <textarea aria-label="汝之所想，皆以言成">/</textarea>
                <div class="composer-toolbar"><button class="round">+</button><span></span><button class="send">&uarr;</button></div>
              </form>
            </div>
          </section>
        </div>
      </section>`;
  });

  const geometry = await page.evaluate(() => {
    const canvas = document.querySelector<HTMLElement>(".task-canvas")!.getBoundingClientRect();
    const composer = document.querySelector<HTMLElement>(".kimi-composer")!;
    const composerBounds = composer.getBoundingClientRect();
    const menuBounds = document.querySelector<HTMLElement>(".slash-menu")!.getBoundingClientRect();
    return {
      composerOverflow: getComputedStyle(composer).overflow,
      menuScrollMaxHeight: parseFloat(getComputedStyle(document.querySelector<HTMLElement>(".slash-menu__scroll")!).maxHeight),
      menuAboveComposer: menuBounds.bottom <= composerBounds.top,
      menuInsideCanvas: menuBounds.top >= canvas.top && menuBounds.bottom <= canvas.bottom,
      menuHeight: menuBounds.height,
    };
  });

  expect(geometry.composerOverflow).toBe("visible");
  expect(geometry.menuScrollMaxHeight).toBeGreaterThanOrEqual(300);
  expect(geometry.menuScrollMaxHeight).toBeLessThanOrEqual(340);
  expect(geometry.menuAboveComposer).toBe(true);
  expect(geometry.menuInsideCanvas).toBe(true);
  expect(geometry.menuHeight).toBeGreaterThan(0);
});

test("bottom diff preview is restored from the latest run after reopening a session", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.evaluate(async () => {
    const modulePath = "/src/lib/ipc.ts";
    const { IpcClient } = await import(modulePath) as {
      IpcClient: { prototype: { request: (method: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>> } };
    };
    IpcClient.prototype.request = async (method, params = {}) => {
      if (method === "session.get_history") return { messages: [], run_stats: {} };
      if (method === "workspace.tree") return { nodes: [] };
      if (method === "change.list") {
        if (params.run_id !== "run-history") throw new Error("unexpected run id");
        return {
          changes: [{
            path: "src/App.vue",
            index_status: " ",
            worktree_status: "M",
            run_id: "run-history",
            agent_owned: true,
            revertible: true,
            additions: 12,
            deletions: 3,
          }],
        };
      }
      return {};
    };

    const root = document.querySelector("#app") as HTMLElement & {
      __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } };
    };
    const state = root.__vue_app__?._instance?.setupState;
    if (!state) throw new Error("Vue application state is unavailable");
    const project = { workspace_id: "workspace-history", name: "History", path: "F:/history", archived: false };
    state.workspace = project;
    state.workspaces = [project];
    state.sessions = [{
      session_id: "session-history",
      title: "Historical task",
      status: "active",
      updated_at: "",
      archived: false,
      pinned: false,
      workspace_id: "workspace-history",
      latest_run_id: "run-history",
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_elapsed_s: 0,
    }];
    const chooseTask = state.chooseTask as ((id: string) => Promise<void>) | undefined;
    if (!chooseTask) throw new Error("chooseTask is unavailable");
    await chooseTask("session-history");
  });

  const preview = page.locator(".bottom-diff-preview");
  await expect(preview).toBeVisible();
  await expect(preview).toContainText("本轮修改 1 个文件");
  await expect(preview).toContainText("+12");
  await expect(preview).toContainText("−3");
});

test("compaction context stays hidden while restored user turns remain separate", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.evaluate(async () => {
    const modulePath = "/src/lib/ipc.ts";
    const { IpcClient } = await import(modulePath) as {
      IpcClient: { prototype: { request: (method: string) => Promise<Record<string, unknown>> } };
    };
    IpcClient.prototype.request = async (method) => {
      if (method === "workspace.tree") return { nodes: [] };
      if (method === "session.get_history") {
        return {
          messages: [
            { role: "user", content: "第一条真实请求", run_id: "run-1" },
            { role: "assistant", content: "第一条历史输出", run_id: "run-1" },
            {
              role: "user",
              content: "This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.\n\nSummary:\n## 1. Original Goal\nInternal only",
            },
            { role: "assistant", content: "Understood, I'll continue from this summary." },
            { role: "user", content: "第二条真实请求", run_id: "run-2" },
            { role: "assistant", content: "第二条历史输出", run_id: "run-2" },
          ],
          run_stats: {},
        };
      }
      return {};
    };

    const root = document.querySelector("#app") as HTMLElement & {
      __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } };
    };
    const state = root.__vue_app__?._instance?.setupState;
    if (!state) throw new Error("Vue application state is unavailable");
    const project = { workspace_id: "workspace-history", name: "History", path: "F:/history", archived: false };
    state.workspace = project;
    state.workspaces = [project];
    state.sessions = [{
      session_id: "session-history",
      title: "Historical task",
      status: "active",
      updated_at: "",
      archived: false,
      pinned: false,
      workspace_id: "workspace-history",
      latest_run_id: null,
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_elapsed_s: 0,
    }];
    const chooseTask = state.chooseTask as ((id: string) => Promise<void>) | undefined;
    if (!chooseTask) throw new Error("chooseTask is unavailable");
    await chooseTask("session-history");
  });

  await expect(page.locator(".timeline-user-message")).toHaveCount(2);
  await expect(page.locator(".timeline-user-message").nth(0)).toHaveText("第一条真实请求");
  await expect(page.locator(".timeline-user-message").nth(1)).toHaveText("第二条真实请求");
  await expect(page.getByText("第一条历史输出", { exact: true })).toBeVisible();
  await expect(page.getByText("第二条历史输出", { exact: true })).toBeVisible();
  await expect(page.getByText(/This session is being continued/)).toHaveCount(0);
  await expect(page.getByText("Understood, I'll continue from this summary.", { exact: true })).toHaveCount(0);
});

test("focused long task titles auto-scroll without a horizontal scrollbar", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const longTitle = "这是一个非常长的任务名称用于验证聚焦之后自动横向滚动并且不会出现任何横向滚动条";

  await page.locator("#app").evaluate((root, title) => {
    const app = (root as HTMLElement & {
      __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } };
    }).__vue_app__;
    const state = app?._instance?.setupState;
    if (!state) throw new Error("Vue application state is unavailable");
    state.sessions = [{
      session_id: "session-long-title",
      title,
      status: "waiting_for_input",
      updated_at: "",
      archived: false,
      pinned: false,
      workspace_id: null,
      latest_run_id: null,
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_elapsed_s: 0,
    }];
  }, longTitle);

  const row = page.getByRole("button", { name: longTitle, exact: true });
  const title = row.locator("[data-auto-scroll-title]");
  await expect(row).toBeVisible();
  await row.focus();

  const geometry = await title.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    scrollbarWidth: getComputedStyle(element).scrollbarWidth,
    rowOverflowX: getComputedStyle(element.closest("button")!).overflowX,
  }));
  expect(geometry.scrollWidth).toBeGreaterThan(geometry.clientWidth);
  expect(geometry.scrollbarWidth).toBe("none");
  expect(geometry.rowOverflowX).toBe("hidden");
  await expect.poll(() => title.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);

  await page.getByRole("button", { name: /新建任务/ }).focus();
  await expect.poll(() => title.evaluate((element) => element.scrollLeft)).toBe(0);
});

test("workspace panel collapses smoothly before it is removed", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("#app").evaluate((root) => {
    const app = (root as HTMLElement & { __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } } }).__vue_app__;
    const state = app?._instance?.setupState;
    if (!state) throw new Error("Vue application state is unavailable");
    state.workspace = { workspace_id: "workspace-fixture", name: "Fixture", path: "F:/fixture", archived: false };
    state.sessions = [{ session_id: "session-fixture", title: "Fixture task", status: "active", updated_at: "", archived: false, pinned: false, workspace_id: "workspace-fixture" }];
    state.activeId = "session-fixture";
  });

  const workspaceToggle = page.getByRole("button", { name: "工作区" });
  const layout = page.locator(".work-layout");
  const inspector = page.locator(".project-inspector");
  await expect(workspaceToggle).toHaveAttribute("aria-expanded", "true");
  await expect(inspector).toBeVisible();

  await workspaceToggle.click();
  await expect(workspaceToggle).toHaveAttribute("aria-expanded", "false");
  await expect(layout).toHaveClass(/no-inspector/);
  await expect(inspector).toBeAttached();
  await expect.poll(() => inspector.count()).toBe(0);

  const columns = await layout.evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(columns.split(" ").map(parseFloat).slice(-2)).toEqual([0, 0]);
});

test("new task, keyboard shortcut, and more tools remain interactive", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.getByRole("button", { name: "全部任务", exact: true }).click();
  await expect(page.getByRole("heading", { name: "全部任务", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /新建任务/ }).click();
  await expect(page.getByRole("heading", { name: "心念为引，一言功毕", exact: true })).toBeVisible();
  await expect(page.getByPlaceholder("汝之所想，皆以言成")).toBeFocused();

  await page.getByPlaceholder("汝之所想，皆以言成").fill("临时内容");
  await page.keyboard.press("Control+K");
  await expect(page.getByPlaceholder("汝之所想，皆以言成")).toHaveValue("");
  await expect(page.getByPlaceholder("汝之所想，皆以言成")).toBeFocused();

  await page.getByRole("button", { name: "更多", exact: true }).click();
  await expect(page.getByRole("button", { name: "更多", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: "浏览器连接", exact: true })).toBeVisible();
  // 通用问答入口暂时隐藏（App.vue chatEntryVisible=false），恢复后改回 toBeVisible
  await expect(page.getByRole("button", { name: "通用问答", exact: true })).not.toBeVisible();
  await expect(page).toHaveScreenshot("sidebar-more-tools-1280.png", { fullPage: true });
  await page.getByRole("button", { name: "更多", exact: true }).click();
  await expect(page.getByRole("button", { name: "浏览器连接", exact: true })).toBeHidden();
});

test("slash menu groups commands and supports keyboard selection", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const launcherInput = page.getByPlaceholder("汝之所想，皆以言成");

  await launcherInput.fill("/");
  const slashMenu = page.getByRole("listbox", { name: "斜杠命令与技能" });
  await expect(slashMenu).toBeVisible();
  await expect(slashMenu.getByRole("region", { name: "命令" }).getByRole("option")).toHaveCount(3);
  await expect(slashMenu.getByRole("region", { name: "技能" }).getByRole("option")).toHaveCount(12);
  await expect(slashMenu.getByRole("option", { name: /\/frontend-design/ })).toBeVisible();
  await expect(slashMenu.getByRole("option", { name: /\/plan/ })).toHaveAttribute("aria-selected", "true");
  await expect(slashMenu.getByText("正在使用内建技能目录，连接本地服务后会同步项目与用户技能")).toBeVisible();
  await expect(page).toHaveScreenshot("slash-command-menu-v3-1280.png", { fullPage: true });

  await page.keyboard.press("ArrowDown");
  await expect(slashMenu.getByRole("option", { name: /\/edits/ })).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Enter");
  await expect(launcherInput).toHaveValue("/edits ");
  await expect(launcherInput).toBeFocused();
  await expect(slashMenu).toBeHidden();

  await launcherInput.fill("/auto");
  await page.keyboard.press("Enter");
  await expect(launcherInput).toHaveValue("/auto ");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alertdialog", { name: "高风险权限提示" })).toBeVisible();
  await page.getByRole("button", { name: "取消", exact: true }).click();

  await launcherInput.fill("/pla");
  await expect(slashMenu.getByRole("option")).toHaveCount(1);
  await expect(slashMenu.getByRole("option", { name: /\/plan/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(slashMenu).toBeHidden();
});

test("new-task controls expose project and permission workflows", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.getByRole("button", { name: "选择本地项目", exact: true }).click();
  await expect(page.getByRole("menu", { name: "选择项目" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "搜索工作空间" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: /打开本地文件夹/ })).toBeVisible();
  await expect(page).toHaveScreenshot("launcher-project-menu-1280.png", { fullPage: true });

  await page.getByRole("button", { name: "标准审批", exact: true }).click();
  await expect(page.getByRole("menu", { name: "权限模式" })).toBeVisible();
  await expect(page.getByRole("menu", { name: "权限模式" }).getByRole("menuitemcheckbox")).toHaveCount(1);
  await expect(page.getByRole("menu", { name: "权限模式" }).getByText("计划模式")).toHaveCount(0);
  await expect(page.getByRole("menu", { name: "权限模式" }).getByText("允许编辑")).toHaveCount(0);
  await expect(page).toHaveScreenshot("launcher-permission-menu-1280.png", { fullPage: true });
  await page.getByRole("menuitemcheckbox", { name: /允许全部权限/ }).click();
  await expect(page.getByRole("alertdialog", { name: "高风险权限提示" })).toBeVisible();
  await expect(page).toHaveScreenshot("launcher-permission-confirm-1280.png", { fullPage: true });
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("alertdialog", { name: "高风险权限提示" })).toBeHidden();
});

test("automation page communicates its local service integration state", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /自动化/ }).click();
  await expect(page.getByRole("heading", { name: "定时任务", exact: true })).toBeVisible();
  await expect(page.getByText("暂无定时任务")).toBeVisible();
  await expect(page).toHaveScreenshot("agent-automations-1280.png", { fullPage: true });
});

test("sidebar keeps the 952px boundary and auto-collapses below it", async ({ page }) => {
  await page.setViewportSize({ width: 952, height: 640 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const navigationToggle = page.getByRole("button", { name: "收起导航" });
  await expect(navigationToggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: /新建任务/ })).toBeVisible();

  await page.setViewportSize({ width: 952, height: 639 });
  await expect(page.getByRole("button", { name: "展开导航" })).toHaveAttribute("aria-expanded", "false");

  await page.setViewportSize({ width: 952, height: 640 });
  await expect(page.getByRole("button", { name: "收起导航" })).toHaveAttribute("aria-expanded", "true");

  await page.setViewportSize({ width: 951, height: 640 });
  const expandNavigation = page.getByRole("button", { name: "展开导航" });
  await expect(expandNavigation).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: /新建任务/ })).toBeHidden();
  await expect(page.getByRole("heading", { name: "心念为引，一言功毕", exact: true })).toBeVisible();

  await expandNavigation.click();
  await expect(page.getByRole("button", { name: /新建任务/ })).toBeVisible();
  await page.getByRole("button", { name: "更多", exact: true }).click();
  await expect(page.getByRole("button", { name: "浏览器连接" })).toBeVisible();
  await page.getByPlaceholder("汝之所想，皆以言成").fill("/");
  await expect(page.getByRole("listbox", { name: "斜杠命令与技能" })).toBeVisible();
  await expect(page).toHaveScreenshot("agent-sidebar-v6-951.png", { fullPage: true });

  await page.setViewportSize({ width: 952, height: 640 });
  await expect(page.getByRole("button", { name: "收起导航" })).toHaveAttribute("aria-expanded", "true");
});

test("sidebar content keeps its width while the navigation viewport collapses", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const sidebar = page.locator(".agent-sidebar");
  const viewport = page.locator(".sidebar-viewport");
  await expect(sidebar).toHaveCSS("width", "268px");
  await page.getByRole("button", { name: "收起导航" }).click();

  const geometry = await page.evaluate(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 80));
    const sidebar = document.querySelector<HTMLElement>(".agent-sidebar")!;
    const viewport = document.querySelector<HTMLElement>(".sidebar-viewport")!;
    const command = document.querySelector<HTMLElement>(".new-task-button")!;
    return {
      sidebarWidth: sidebar.getBoundingClientRect().width,
      viewportWidth: viewport.getBoundingClientRect().width,
      commandWidth: command.getBoundingClientRect().width,
    };
  });

  expect(geometry.viewportWidth).toBeGreaterThan(0);
  expect(geometry.viewportWidth).toBeLessThan(268);
  expect(geometry.sidebarWidth).toBe(268);
  expect(geometry.commandWidth).toBeGreaterThan(240);
  await expect(page.getByRole("button", { name: /新建任务/ })).toBeHidden();

  await page.getByRole("button", { name: "展开导航" }).click();
  const expandedGeometry = await page.evaluate(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 80));
    const sidebar = document.querySelector<HTMLElement>(".agent-sidebar")!;
    const viewport = document.querySelector<HTMLElement>(".sidebar-viewport")!;
    const command = document.querySelector<HTMLElement>(".new-task-button")!;
    return {
      sidebarWidth: sidebar.getBoundingClientRect().width,
      viewportWidth: viewport.getBoundingClientRect().width,
      commandWidth: command.getBoundingClientRect().width,
    };
  });

  expect(expandedGeometry.viewportWidth).toBeGreaterThan(0);
  expect(expandedGeometry.viewportWidth).toBeLessThan(268);
  expect(expandedGeometry.sidebarWidth).toBe(268);
  expect(expandedGeometry.commandWidth).toBeGreaterThan(240);
  await expect(page.getByRole("button", { name: /新建任务/ })).toBeVisible();
});

test("sidebar resizer clamps its range and collapses after an intentional over-pull", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript(() => localStorage.removeItem("sztu.sidebarWidth"));
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const shell = page.locator(".kimi-shell");
  const resizer = page.getByRole("separator", { name: "调整导航宽度" });
  const dragTo = async (targetX: number, release = true) => {
    const bounds = await resizer.boundingBox();
    if (!bounds) throw new Error("Sidebar resizer is unavailable");
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.mouse.down();
    await page.mouse.move(targetX, bounds.y + bounds.height / 2, { steps: 5 });
    if (release) await page.mouse.up();
  };

  await dragTo(520);
  await expect(resizer).toHaveAttribute("aria-valuenow", "360");
  expect(await page.evaluate(() => localStorage.getItem("sztu.sidebarWidth"))).toBe("360");

  await dragTo(210);
  await expect(resizer).toHaveAttribute("aria-valuenow", "224");
  await expect(shell).not.toHaveClass(/sidebar-collapsed/);

  await dragTo(150, false);
  await expect(shell).toHaveClass(/sidebar-collapse-armed/);
  await expect(shell).not.toHaveClass(/sidebar-collapsed/);
  await page.mouse.up();

  await expect(shell).toHaveClass(/sidebar-collapsed/);
  await expect(page.getByRole("button", { name: "展开导航" })).toHaveAttribute("aria-expanded", "false");
});

test("settings opens as an appearance dialog from the workbench footer", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "外观" })).toBeVisible();
  await expect(dialog.getByRole("radio", { name: "跟随系统" })).toBeVisible();
  await dialog.getByRole("button", { name: "通用" }).click();
  await expect(dialog.getByText("系统设置")).toBeVisible();
  await dialog.getByRole("button", { name: "关闭设置" }).click();
  await expect(dialog).toBeHidden();
});

test("about settings displays the desktop version and project link", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });

  await dialog.getByRole("button", { name: "关于", exact: true }).click();
  await expect(dialog.getByRole("heading", { name: "关于", exact: true })).toBeVisible();
  await expect(dialog.getByText("v0.1.0", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "打开项目链接" })).toContainText("github.com/rojim666/SztuCode");
});

test("appearance settings offer distinct interface font previews", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  const fontGroup = dialog.getByRole("radiogroup", { name: "界面字体" });

  await expect(fontGroup.getByRole("radio")).toHaveCount(9);
  await fontGroup.getByRole("radio", { name: "思源黑体" }).click();
  expect(await page.locator("html").evaluate((root) => root.style.getPropertyValue("--font-ui"))).toContain("Noto Sans SC");
  await expect(fontGroup.getByRole("radio", { name: "思源黑体" })).toHaveAttribute("aria-checked", "true");

  await fontGroup.getByRole("radio", { name: "楷体" }).click();
  expect(await page.locator("html").evaluate((root) => root.style.getPropertyValue("--font-ui"))).toContain("KaiTi");
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("sztu.appearance") || "{}").uiFont)).toBe("kaiti");
});

test("interface font size updates the full typography scale and persists", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });

  const readFontSizes = () => page.evaluate(() => ({
    brand: parseFloat(getComputedStyle(document.querySelector<HTMLElement>(".sidebar-brand h1")!).fontSize),
    launcher: parseFloat(getComputedStyle(document.querySelector<HTMLElement>(".launcher-heading h1")!).fontSize),
    newTask: parseFloat(getComputedStyle(document.querySelector<HTMLElement>(".new-task-button")!).fontSize),
    textarea: parseFloat(getComputedStyle(document.querySelector<HTMLElement>(".landing-composer textarea")!).fontSize),
    settingsTitle: parseFloat(getComputedStyle(document.querySelector<HTMLElement>(".settings-pane-title h2")!).fontSize),
  }));

  const before = await readFontSizes();
  await dialog.getByRole("button", { name: "增大字号" }).click();
  await dialog.getByRole("button", { name: "增大字号" }).click();
  await expect(dialog.locator(".stepper output")).toHaveText("16px");

  const after = await readFontSizes();
  expect(after.brand).toBeGreaterThan(before.brand);
  expect(after.launcher).toBeGreaterThan(before.launcher);
  expect(after.newTask).toBeGreaterThan(before.newTask);
  expect(after.textarea).toBeGreaterThan(before.textarea);
  expect(after.settingsTitle).toBeGreaterThan(before.settingsTitle);
  expect(await page.locator("html").evaluate((root) => root.style.getPropertyValue("--text-body"))).toBe("16px");

  await dialog.getByRole("button", { name: "增大字号" }).click();
  await dialog.getByRole("button", { name: "增大字号" }).click();
  await expect(dialog.locator(".stepper output")).toHaveText("18px");
  await expect(dialog.getByRole("button", { name: "增大字号" })).toBeDisabled();
  const overflow = await page.evaluate(() => Object.fromEntries(
    [".settings-dialog__content", ".agent-sidebar", ".starter-tasks"].map((selector) => {
      const element = document.querySelector<HTMLElement>(selector)!;
      return [selector, element.scrollWidth - element.clientWidth];
    }),
  ));
  expect(overflow).toEqual({
    ".settings-dialog__content": 0,
    ".agent-sidebar": 0,
    ".starter-tasks": 0,
  });

  await dialog.getByRole("button", { name: "关闭设置" }).click();
  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await page.locator("html").evaluate((root) => root.style.getPropertyValue("--text-body"))).toBe("18px");
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("sztu.appearance") || "{}").fontSize)).toBe(18);
});

test("regional transparency controls update each workspace surface independently", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  await expect(dialog.getByRole("slider", { name: "侧栏与顶部栏透明度" })).toBeDisabled();
  await dialog.getByRole("radio", { name: "网格" }).click();
  await expect(dialog.getByRole("slider", { name: "侧栏与顶部栏透明度" })).toBeEnabled();
  await page.locator(".kimi-shell").evaluate((shell) => {
    const fixture = document.createElement("aside");
    fixture.className = "project-inspector file-rail";
    fixture.dataset.transparencyFixture = "inspector";
    fixture.style.cssText = "position:fixed;left:-100px;top:-100px;width:10px;height:10px;display:block";
    shell.append(fixture);
  });

  const setSlider = async (name: string, value: number) => {
    await dialog.getByRole("slider", { name }).evaluate((input, nextValue) => {
      const slider = input as HTMLInputElement;
      slider.value = String(nextValue);
      slider.dispatchEvent(new Event("input", { bubbles: true }));
    }, value);
  };
  await setSlider("侧栏与顶部栏透明度", 60);
  await setSlider("会话区透明度", 50);
  await setSlider("输入框透明度", 40);
  await setSlider("右侧功能栏透明度", 30);

  const result = await page.evaluate(() => {
    const alpha = (selector: string) => {
      const color = getComputedStyle(document.querySelector<HTMLElement>(selector)!).backgroundColor;
      const modernColorAlpha = color.match(/\/\s*([\d.]+)\s*\)$/);
      if (modernColorAlpha) return Math.round(Number(modernColorAlpha[1]) * 255);
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const context = canvas.getContext("2d")!;
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      return context.getImageData(0, 0, 1, 1).data[3];
    };
    const root = document.documentElement;
    return {
      variables: {
        chrome: root.style.getPropertyValue("--chrome-surface-opacity"),
        conversation: root.style.getPropertyValue("--conversation-surface-opacity"),
        composer: root.style.getPropertyValue("--composer-surface-opacity"),
        inspector: root.style.getPropertyValue("--inspector-surface-opacity"),
      },
      alpha: {
        chrome: alpha(".kimi-titlebar"),
        conversation: alpha(".kimi-main"),
        composer: alpha(".task-launcher .composer-input-shell"),
        inspector: alpha('[data-transparency-fixture="inspector"]'),
      },
      persisted: JSON.parse(localStorage.getItem("sztu.appearance") || "{}"),
    };
  });

  expect(result.variables).toEqual({ chrome: "40%", conversation: "50%", composer: "60%", inspector: "70%" });
  expect(result.alpha.chrome).toBeCloseTo(102, 0);
  expect(result.alpha.conversation).toBeCloseTo(128, 0);
  expect(result.alpha.composer).toBeCloseTo(153, 0);
  expect(result.alpha.inspector).toBeCloseTo(179, 0);
  expect(result.persisted).toMatchObject({
    chromeTransparency: 60,
    conversationTransparency: 50,
    composerTransparency: 40,
    inspectorTransparency: 30,
  });

  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await page.locator("html").evaluate((root) => ({
    chrome: root.style.getPropertyValue("--chrome-surface-opacity"),
    conversation: root.style.getPropertyValue("--conversation-surface-opacity"),
    composer: root.style.getPropertyValue("--composer-surface-opacity"),
    inspector: root.style.getPropertyValue("--inspector-surface-opacity"),
  }))).toEqual({ chrome: "40%", conversation: "50%", composer: "60%", inspector: "70%" });
});

test("preset wallpaper is visible through the workspace surfaces", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  await dialog.getByRole("radio", { name: "网格" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-wallpaper", "grid");
  await dialog.getByRole("button", { name: "关闭设置" }).click();

  const wallpaper = await page.evaluate(() => {
    const alpha = (selector: string) => {
      const color = getComputedStyle(document.querySelector<HTMLElement>(selector)!).backgroundColor;
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const context = canvas.getContext("2d")!;
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      return context.getImageData(0, 0, 1, 1).data[3];
    };
    const shell = document.querySelector<HTMLElement>(".kimi-shell")!;
    return {
      texture: getComputedStyle(shell, "::before").backgroundImage,
      titlebarAlpha: alpha(".kimi-titlebar"),
      sidebarViewportAlpha: alpha(".sidebar-viewport"),
      sidebarAlpha: alpha(".kimi-sidebar"),
      mainAlpha: alpha(".kimi-main"),
    };
  });

  expect(wallpaper.texture).not.toBe("none");
  expect(wallpaper.titlebarAlpha).toBeLessThanOrEqual(175);
  expect(wallpaper.sidebarViewportAlpha).toBeLessThanOrEqual(175);
  expect(wallpaper.sidebarAlpha).toBe(0);
  expect(wallpaper.mainAlpha).toBeLessThanOrEqual(165);
});

test("dark appearance keeps the wallpaper visible and launcher surfaces readable", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  await dialog.getByRole("radio", { name: "深色" }).click();
  await dialog.getByRole("radio", { name: "网格" }).click();
  await dialog.getByRole("button", { name: "关闭设置" }).click();
  await expect.poll(() => page.locator(".kimi-shell").evaluate((shell) => (
    Number(getComputedStyle(shell, "::before").opacity)
  ))).toBeGreaterThanOrEqual(0.69);

  const appearance = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const shell = document.querySelector<HTMLElement>(".kimi-shell")!;
    const heading = document.querySelector<HTMLElement>(".launcher-heading h1")!;
    const starter = document.querySelector<HTMLElement>(".starter-tasks button")!;
    const textColorProbe = document.createElement("span");
    textColorProbe.style.color = "var(--text)";
    document.body.append(textColorProbe);
    const expectedTextColor = getComputedStyle(textColorProbe).color;
    textColorProbe.remove();
    return {
      theme: document.documentElement.dataset.appTheme,
      wallpaper: document.documentElement.dataset.wallpaper,
      texture: getComputedStyle(shell, "::before").backgroundImage,
      wallpaperOpacity: Number(getComputedStyle(shell, "::before").opacity),
      lightWallpaperOpacity: Number(root.getPropertyValue("--wallpaper-opacity")),
      headingColor: getComputedStyle(heading).color,
      expectedTextColor,
      starterBackground: getComputedStyle(starter).backgroundColor,
    };
  });

  expect(appearance.theme).toBe("dark");
  expect(appearance.wallpaper).toBe("grid");
  expect(appearance.texture).not.toBe("none");
  expect(appearance.wallpaperOpacity).toBeGreaterThan(appearance.lightWallpaperOpacity);
  expect(appearance.wallpaperOpacity).toBeGreaterThanOrEqual(0.46);
  expect(appearance.headingColor).toBe(appearance.expectedTextColor);
  expect(appearance.starterBackground).not.toBe("rgb(255, 255, 255)");
});

test("dark workspace keeps enough wallpaper visible through the conversation surface", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("html").evaluate((root) => {
    root.dataset.appTheme = "dark";
    root.dataset.wallpaper = "grid";
  });
  await page.locator(".kimi-main").evaluate((main) => {
    main.innerHTML = `
      <section class="work-page">
        <div class="work-layout no-inspector">
          <section class="task-canvas">
            <header class="work-header">SztuCode</header>
            <div class="task-conversation">
              <div class="task-stream">背景可见性</div>
              <form class="kimi-composer"><textarea></textarea></form>
            </div>
          </section>
        </div>
      </section>`;
  });
  await expect.poll(() => page.locator(".kimi-shell").evaluate((shell) => (
    Number(getComputedStyle(shell, "::before").opacity)
  ))).toBeGreaterThanOrEqual(0.69);

  const result = await page.evaluate(() => {
    const alpha = (selector: string) => {
      const color = getComputedStyle(document.querySelector<HTMLElement>(selector)!).backgroundColor;
      const modernColorAlpha = color.match(/\/\s*([\d.]+)\s*\)$/);
      if (modernColorAlpha) return Math.round(Number(modernColorAlpha[1]) * 255);
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const context = canvas.getContext("2d")!;
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      return context.getImageData(0, 0, 1, 1).data[3];
    };
    const shell = document.querySelector<HTMLElement>(".kimi-shell")!;
    const wallpaperOpacity = Number(getComputedStyle(shell, "::before").opacity);
    const canvasAlpha = alpha(".task-canvas");
    return {
      mainAlpha: alpha(".kimi-main"),
      canvasAlpha,
      headerAlpha: alpha(".work-header"),
      composerAlpha: alpha(".kimi-composer"),
      wallpaperOpacity,
      effectiveWallpaperReveal: wallpaperOpacity * (1 - canvasAlpha / 255),
    };
  });
  expect(result.mainAlpha).toBe(0);
  expect(result.canvasAlpha).toBeLessThanOrEqual(165);
  expect(result.headerAlpha).toBe(0);
  expect(result.composerAlpha).toBeLessThan(255);
  expect(result.wallpaperOpacity).toBeGreaterThanOrEqual(0.69);
  expect(result.effectiveWallpaperReveal).toBeGreaterThanOrEqual(0.24);
});

test("dark files inspector uses readable controls, selection, and syntax colors", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("html").evaluate((root) => {
    root.dataset.appTheme = "dark";
    root.dataset.wallpaper = "grid";
  });
  await page.locator(".kimi-main").evaluate((main) => {
    main.innerHTML = `
      <aside class="project-inspector file-rail" style="width:760px;height:620px">
        <header class="workspace-tab-strip">
          <div class="workspace-open-tab active"><button><span class="workspace-tab-icon"></span><span>文件</span></button></div>
        </header>
        <main class="files-workspace">
          <div class="file-tree-view" style="grid-template-columns:minmax(0,1fr) 6px 220px">
            <section class="file-preview file-preview--files">
              <header><b>appearance.ts</b><small>src/services/appearance.ts</small></header>
              <div class="code-preview">
                <div class="code-preview-meta"><span class="format-badge">TypeScript</span><span>UTF-8</span></div>
                <div class="preview-breadcrumb"><span>src <i>/</i> services <i>/</i> appearance.ts</span></div>
                <div class="code-preview-scroll">
                  <div class="code-line"><span class="line-number">1</span><code><span class="hljs-comment">// theme</span></code></div>
                  <div class="code-line"><span class="line-number">2</span><code><span class="hljs-keyword">const</span> theme = <span class="hljs-string">"dark"</span>;</code></div>
                  <div class="code-line"><span class="line-number">3</span><code><span class="hljs-title function_">applyTheme</span>(<span class="hljs-number">2</span>);</code></div>
                </div>
              </div>
            </section>
            <div class="file-tree-divider"></div>
            <div class="files-body">
              <div class="file-row dir"><span class="row-icon">D</span><span class="row-name">src</span></div>
              <div class="file-row active"><span class="row-icon">F</span><span class="row-name">appearance.ts</span></div>
            </div>
          </div>
        </main>
      </aside>`;
  });

  const colors = await page.evaluate(() => {
    const style = (selector: string) => getComputedStyle(document.querySelector<HTMLElement>(selector)!);
    const channelMax = (color: string) => Math.max(...(color.match(/[\d.]+/g) || []).slice(0, 3).map(Number));
    return {
      tab: style(".workspace-open-tab.active").backgroundColor,
      activeRow: style(".file-row.active").backgroundColor,
      rowText: channelMax(style(".file-row.active .row-name").color),
      folderIcon: channelMax(style(".file-row.dir .row-icon").color),
      codeText: channelMax(style(".code-preview-scroll").color),
      comment: channelMax(style(".hljs-comment").color),
      keyword: channelMax(style(".hljs-keyword").color),
      string: channelMax(style(".hljs-string").color),
      number: channelMax(style(".hljs-number").color),
      overflow: document.querySelector<HTMLElement>(".project-inspector.file-rail")!.scrollWidth
        - document.querySelector<HTMLElement>(".project-inspector.file-rail")!.clientWidth,
    };
  });

  expect(colors.tab).not.toBe("rgb(244, 244, 244)");
  expect(colors.activeRow).not.toBe("rgb(233, 241, 236)");
  expect(colors.activeRow).not.toBe("rgb(255, 255, 255)");
  expect(colors.rowText).toBeGreaterThan(150);
  expect(colors.folderIcon).toBeGreaterThan(150);
  expect(colors.codeText).toBeGreaterThan(180);
  expect(colors.comment).toBeGreaterThan(150);
  expect(colors.keyword).toBeGreaterThan(180);
  expect(colors.string).toBeGreaterThan(180);
  expect(colors.number).toBeGreaterThan(180);
  expect(colors.overflow).toBe(0);
});

test("switching preset textures updates the wallpaper layer immediately", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  const textures = [
    { label: "薄雾", value: "mist" },
    { label: "网格", value: "grid" },
    { label: "纸纹", value: "paper" },
  ];
  const backgrounds: string[] = [];

  for (const texture of textures) {
    await dialog.getByRole("radio", { name: texture.label }).click();
    await expect(page.locator("html")).toHaveAttribute("data-wallpaper", texture.value);
    backgrounds.push(await page.locator(".kimi-shell").evaluate((shell) => getComputedStyle(shell, "::before").backgroundImage));
  }

  expect(backgrounds.every((background) => background !== "none")).toBe(true);
  expect(new Set(backgrounds).size).toBe(textures.length);
});

test("mist wallpaper stays visible beneath the workspace surfaces", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  await dialog.getByRole("radio", { name: "薄雾" }).click();
  await dialog.getByRole("button", { name: "关闭设置" }).click();

  const chrome = await page.evaluate(() => {
    const titlebar = getComputedStyle(document.querySelector<HTMLElement>(".kimi-titlebar")!);
    const sidebar = getComputedStyle(document.querySelector<HTMLElement>(".sidebar-viewport")!);
    const main = document.querySelector<HTMLElement>(".kimi-main")!;
    const canvas = document.createElement("canvas");
    canvas.width = 1;
    canvas.height = 1;
    const context = canvas.getContext("2d")!;
    context.fillStyle = getComputedStyle(main).backgroundColor;
    context.fillRect(0, 0, 1, 1);
    return {
      wallpaper: document.documentElement.dataset.wallpaper,
      titlebarImage: titlebar.backgroundImage,
      titlebarAnimation: titlebar.animationName,
      titlebarAttachment: titlebar.backgroundAttachment,
      sidebarImage: sidebar.backgroundImage,
      sidebarAnimation: sidebar.animationName,
      sidebarAttachment: sidebar.backgroundAttachment,
      mainAlpha: context.getImageData(0, 0, 1, 1).data[3],
    };
  });

  expect(chrome.wallpaper).toBe("mist");
  expect(chrome.titlebarImage).toContain("linear-gradient");
  expect(chrome.sidebarImage).toContain("linear-gradient");
  expect(chrome.titlebarAnimation).toBe("mist-chrome-flow");
  expect(chrome.sidebarAnimation).toBe("mist-chrome-flow");
  expect(chrome.titlebarAttachment).toBe("fixed");
  expect(chrome.sidebarAttachment).toBe("fixed");
  expect(chrome.mainAlpha).toBeLessThanOrEqual(165);
});

test("wallpaper flows through the files inspector surfaces", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("html").evaluate((root) => { root.dataset.wallpaper = "grid"; });
  await page.locator(".kimi-main").evaluate((main) => {
    main.innerHTML = `
      <aside class="project-inspector file-rail">
        <header class="workspace-tab-strip">文件</header>
        <main class="files-workspace">
          <div class="file-tree-view">
            <section class="file-preview file-preview--files empty">
              <div class="files-empty files-preview-placeholder">打开文件</div>
              <div class="code-preview"><div class="code-preview-meta"></div><div class="preview-breadcrumb"></div><div class="code-preview-scroll"></div></div>
            </section>
            <div class="file-tree-divider"></div>
            <div class="files-body">项目文件</div>
          </div>
        </main>
      </aside>`;
  });

  const surfaces = await page.evaluate(() => {
    const alpha = (selector: string) => {
      const color = getComputedStyle(document.querySelector<HTMLElement>(selector)!).backgroundColor;
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const context = canvas.getContext("2d")!;
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      return context.getImageData(0, 0, 1, 1).data[3];
    };
    return {
      inspector: alpha(".project-inspector.file-rail"),
      workspace: alpha(".files-workspace"),
      preview: alpha(".file-preview--files"),
      tree: alpha(".files-body"),
      code: alpha(".code-preview"),
      codeScroll: alpha(".code-preview-scroll"),
    };
  });

  expect(surfaces.inspector).toBeLessThanOrEqual(165);
  expect(surfaces.workspace).toBe(0);
  expect(surfaces.preview).toBe(0);
  expect(surfaces.tree).toBe(0);
  expect(surfaces.code).toBeLessThanOrEqual(210);
  expect(surfaces.codeScroll).toBe(0);
});

test("appearance settings can upload and remove a custom wallpaper", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "设置" }).click();
  const dialog = page.getByRole("dialog", { name: "设置" });
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAACNklEQVR42mNhQAIGBgYCX378yWf8zxDwH8hloCJgZGC48J+RYQMPB8vECxcufEAShwBVDd2E//8Z+hkY/gsw0BQwfmBkZCi8fePyAhCPGWH5//lAJgcD7QHIjgBhUfGH7968usAIDvbvf+/T3ueYIcHDyazIzCMgUgHkeTDQH3D8+vvvJxMwwfkzDBAA2c1C7dROCgDZzcIwwGDAHcCET1JGWppBU1Nj4Bywcf0qhk3rVzMEBfoPTBQwMkIKys72FjC9bv1GqjuAWUhErAGX5KEjRxl8vD0Z2NnZGVxdnBj4eHkZDgPF6BYF16/fYIiOS2L4/PkzmJ8QH8vQ0d5MvxAAgTdv3oBDws7WhoGPj5dBC5gopaWlGPbs3U/7EEAOCb/AUIbrN26C+cGBAeDQoHs5AKwx6ZsNYQBUFoCypBa0TADlhgULF9MnBECWL1k4Fxj/fHDLyytr6FMOoFu+cNEShpa2Trici7MjXsMXLlrK8OnTJ/IdgGw5yNfIBVFNZTmDmZkJgXYgI8OkKdPITwOwkhDdchBYu34Dw9Onz3DqBcnt3ruPcJtARV3nP77KiBeY90HZcEDqgidPnwK9MszbAwPfIAEms4sD1igF2s0E6i4NWKMUaDcTsK82AeiWjwPg/48gu5lfvHjxA9hNegHqLtE17pkYI69euXQB3DcE9dFAfTWgqxxp3z9k/Aiy/Nb1yxvgnVOYI+RkpWaAukvAxCEIFJKgdoIDEjN5OFkiQD6HSQAA0hu+tsnl1ZkAAAAASUVORK5CYII=",
    "base64",
  );

  await dialog.locator('input[type="file"][accept*="image/png"]').setInputFiles({
    name: "workspace-background.png",
    mimeType: "image/png",
    buffer: png,
  });

  await expect(dialog.locator(".settings-error")).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute("data-wallpaper", "custom");
  await expect(dialog.getByText("workspace-background.png")).toBeVisible();
  const persisted = await page.evaluate(() => JSON.parse(localStorage.getItem("sztu.appearance") || "{}"));
  expect(persisted.customWallpaper).toMatch(/^data:image\/webp/);
  expect(persisted.customWallpaperName).toBe("workspace-background.png");
  expect(await page.locator(".kimi-shell").evaluate((shell) => getComputedStyle(shell, "::before").backgroundImage)).not.toBe("none");

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-wallpaper", "custom");
  await page.getByRole("button", { name: "设置" }).click();
  const reopenedDialog = page.getByRole("dialog", { name: "设置" });
  await expect(reopenedDialog.getByText("workspace-background.png")).toBeVisible();

  await reopenedDialog.getByRole("button", { name: "移除背景图" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-wallpaper", "none");
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("sztu.appearance") || "{}").customWallpaper)).toBe("");
});

test("conversation stays flat with a gray workspace boundary", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("#app").evaluate((root) => {
    const app = (root as HTMLElement & { __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } } }).__vue_app__;
    const state = app?._instance?.setupState;
    if (!state) throw new Error("Vue application state is unavailable");
    const workspace = { workspace_id: "workspace-fixture", name: "Fixture", path: "F:/fixture", archived: false };
    state.workspace = workspace;
    state.workspaces = [workspace];
    state.sessions = [{
      session_id: "session-fixture", title: "Fixture task", status: "active", updated_at: "",
      archived: false, pinned: false, workspace_id: "workspace-fixture",
      total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0,
    }];
    state.activeId = "session-fixture";
    state.inspectorOpen = true;
    state.inspectorRendered = true;
  });

  const geometry = await page.locator(".work-layout").evaluate((layout) => {
    const main = document.querySelector<HTMLElement>(".kimi-main")!;
    const titlebar = document.querySelector<HTMLElement>(".kimi-titlebar")!;
    const sidebarViewport = document.querySelector<HTMLElement>(".sidebar-viewport")!;
    const sidebar = document.querySelector<HTMLElement>(".kimi-sidebar")!;
    const sidebarFooter = document.querySelector<HTMLElement>(".sidebar-footer")!;
    const workHeader = layout.closest(".work-page")!.querySelector<HTMLElement>(".work-header")!;
    const conversation = layout.querySelector<HTMLElement>(".task-canvas")!;
    const inspector = layout.querySelector<HTMLElement>(".project-inspector.file-rail")!;
    const inspectorHeader = inspector.querySelector<HTMLElement>(".workspace-tab-strip")!;
    const divider = layout.querySelector<HTMLElement>(".layout-divider")!;
    const mainStyle = getComputedStyle(main);
    const titlebarStyle = getComputedStyle(titlebar);
    const sidebarViewportStyle = getComputedStyle(sidebarViewport);
    const sidebarStyle = getComputedStyle(sidebar);
    const sidebarFooterStyle = getComputedStyle(sidebarFooter);
    const workHeaderStyle = getComputedStyle(workHeader);
    const conversationStyle = getComputedStyle(conversation);
    const inspectorStyle = getComputedStyle(inspector);
    const inspectorHeaderStyle = getComputedStyle(inspectorHeader);
    const dividerStyle = getComputedStyle(divider);
    const conversationRect = conversation.getBoundingClientRect();
    const inspectorRect = inspector.getBoundingClientRect();
    const dividerRect = divider.getBoundingClientRect();
    return {
      mainMarginRight: mainStyle.marginRight,
      mainMarginBottom: mainStyle.marginBottom,
      mainShadow: mainStyle.boxShadow,
      titlebarBackground: titlebarStyle.backgroundColor,
      titlebarBorder: titlebarStyle.borderBottomWidth,
      sidebarShadow: sidebarViewportStyle.boxShadow,
      sidebarViewportBackground: sidebarViewportStyle.backgroundColor,
      sidebarBackground: sidebarStyle.backgroundColor,
      sidebarBorder: sidebarStyle.borderRightWidth,
      sidebarFooterBorder: sidebarFooterStyle.borderTopWidth,
      workHeaderBorder: workHeaderStyle.borderBottomWidth,
      mainTopLeftRadius: mainStyle.borderTopLeftRadius,
      mainTopRightRadius: mainStyle.borderTopRightRadius,
      mainBottomRightRadius: mainStyle.borderBottomRightRadius,
      mainBottomLeftRadius: mainStyle.borderBottomLeftRadius,
      conversationTopLeftRadius: conversationStyle.borderTopLeftRadius,
      conversationTopRightRadius: conversationStyle.borderTopRightRadius,
      conversationBottomRightRadius: conversationStyle.borderBottomRightRadius,
      conversationBottomLeftRadius: conversationStyle.borderBottomLeftRadius,
      conversationShadow: conversationStyle.boxShadow,
      conversationBorder: conversationStyle.borderTopWidth,
      inspectorRadius: inspectorStyle.borderRadius,
      inspectorShadow: inspectorStyle.boxShadow,
      inspectorBorder: inspectorStyle.borderTopWidth,
      inspectorHeaderBorder: inspectorHeaderStyle.borderBottomWidth,
      dividerBackground: dividerStyle.backgroundColor,
      panelGap: inspectorRect.left - conversationRect.right,
      dividerWidth: dividerRect.width,
      inspectorRightGap: window.innerWidth - inspectorRect.right,
      inspectorBottomGap: window.innerHeight - inspectorRect.bottom,
    };
  });

  expect(geometry.mainMarginRight).toBe("0px");
  expect(geometry.mainMarginBottom).toBe("0px");
  expect(geometry.titlebarBackground).toBe("rgb(249, 250, 251)");
  expect(geometry.titlebarBorder).toBe("0px");
  expect(geometry.mainShadow).toBe("none");
  expect(geometry.sidebarShadow).toBe("none");
  expect(geometry.sidebarViewportBackground).toBe(geometry.titlebarBackground);
  expect(geometry.sidebarBackground).toBe("rgb(249, 250, 251)");
  expect(geometry.sidebarBackground).toBe(geometry.titlebarBackground);
  expect(geometry.sidebarBorder).toBe("0px");
  expect(geometry.sidebarFooterBorder).toBe("0px");
  expect(geometry.workHeaderBorder).toBe("0px");
  expect(geometry.mainTopLeftRadius).toBe("0px");
  expect(geometry.mainTopRightRadius).toBe("0px");
  expect(geometry.mainBottomRightRadius).toBe("0px");
  expect(geometry.mainBottomLeftRadius).toBe("0px");
  expect(geometry.conversationTopLeftRadius).toBe("0px");
  expect(geometry.conversationTopRightRadius).toBe("0px");
  expect(geometry.conversationBottomRightRadius).toBe("0px");
  expect(geometry.conversationBottomLeftRadius).toBe("0px");
  expect(geometry.conversationShadow).toBe("none");
  expect(geometry.conversationBorder).toBe("0px");
  expect(geometry.inspectorRadius).toBe("0px");
  expect(geometry.inspectorShadow).toBe("none");
  expect(geometry.inspectorBorder).toBe("0px");
  expect(geometry.inspectorHeaderBorder).toBe("0px");
  expect(geometry.dividerBackground).toBe("rgb(229, 231, 235)");
  expect(geometry.panelGap).toBe(1);
  expect(geometry.dividerWidth).toBe(1);
  expect(geometry.inspectorRightGap).toBeLessThanOrEqual(1);
  expect(geometry.inspectorBottomGap).toBeLessThanOrEqual(1);

  const darkChromeBackgrounds = await page.locator("html").evaluate((root) => {
    root.dataset.appTheme = "dark";
    return [".kimi-titlebar", ".sidebar-viewport", ".kimi-sidebar"].map((selector) =>
      getComputedStyle(document.querySelector<HTMLElement>(selector)!).backgroundColor,
    );
  });
  expect(new Set(darkChromeBackgrounds).size).toBe(1);
  expect(darkChromeBackgrounds[0]).toBe("rgb(40, 45, 47)");
});

test("navigation toggle blends into the sidebar chrome at rest", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const readChrome = () => page.evaluate(() => {
    const background = (selector: string) =>
      getComputedStyle(document.querySelector<HTMLElement>(selector)!).backgroundColor;
    const border = getComputedStyle(document.querySelector<HTMLElement>(".nav-toggle")!).borderTopColor;
    return {
      titlebar: background(".kimi-titlebar"),
      sidebar: background(".sidebar-viewport"),
      toggleWrap: background(".nav-toggle-wrap"),
      toggle: background(".nav-toggle"),
      toggleBorder: border,
    };
  });

  expect(await readChrome()).toEqual({
    titlebar: "rgb(249, 250, 251)",
    sidebar: "rgb(249, 250, 251)",
    toggleWrap: "rgba(0, 0, 0, 0)",
    toggle: "rgba(0, 0, 0, 0)",
    toggleBorder: "rgba(0, 0, 0, 0)",
  });

  await page.locator("html").evaluate((root) => { root.dataset.appTheme = "dark"; });
  await page.waitForTimeout(180);
  expect(await readChrome()).toEqual({
    titlebar: "rgb(40, 45, 47)",
    sidebar: "rgb(40, 45, 47)",
    toggleWrap: "rgba(0, 0, 0, 0)",
    toggle: "rgba(0, 0, 0, 0)",
    toggleBorder: "rgba(0, 0, 0, 0)",
  });
});

test("dark theme keeps sidebar and conversation content readable", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("#app").evaluate((root) => {
    const app = (root as HTMLElement & { __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } } }).__vue_app__;
    const state = app?._instance?.setupState;
    if (!state) throw new Error("Vue application state is unavailable");
    const workspace = { workspace_id: "workspace-dark", name: "Dark theme", path: "F:/dark", archived: false };
    state.workspace = workspace;
    state.workspaces = [workspace];
    state.sessions = [{
      session_id: "session-dark", title: "深色主题会话", status: "active", updated_at: "",
      archived: false, pinned: false, workspace_id: "workspace-dark",
      total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0,
    }];
    state.activeId = "session-dark";
  });
  await expect(page.locator(".sidebar-session:has(.project-task.active)")).toBeVisible();
  await page.locator("html").evaluate((root) => { root.dataset.appTheme = "dark"; });
  await page.waitForTimeout(180);

  const darkConversationTheme = await page.locator(".execution-timeline").evaluate((timeline) => {
    timeline.innerHTML = `
      <article class="timeline-step">
        <div class="thinking-panel"><button><span class="thinking-panel__preview">分析项目结构与关键模块</span></button></div>
        <div class="token-stream markdown-body"><hr><pre><code>用户目标 -> 项目上下文 -> Agent 规划</code></pre></div>
      </article>`;
    const style = (selector: string) => getComputedStyle(document.querySelector<HTMLElement>(selector)!);
    return {
      selectedBackground: style(".sidebar-session:has(.project-task.active)").backgroundColor,
      sidebarToolColor: style(".sidebar-tools button").color,
      thinkingColor: style(".thinking-panel__preview").color,
      codeBackground: style(".markdown-body pre").backgroundColor,
      codeColor: style(".markdown-body pre").color,
      codeBorder: style(".markdown-body pre").borderTopColor,
      dividerBackground: style(".markdown-body hr").backgroundColor,
    };
  });
  expect(darkConversationTheme).toEqual({
    selectedBackground: "rgb(58, 65, 68)",
    sidebarToolColor: "rgb(168, 176, 179)",
    thinkingColor: "rgb(168, 176, 179)",
    codeBackground: "rgb(40, 45, 47)",
    codeColor: "rgb(237, 240, 241)",
    codeBorder: "rgb(55, 61, 63)",
    dividerBackground: "rgb(74, 82, 85)",
  });
});

test("Think replays a large thinking chunk from start to finish", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const target = "先检查项目结构，再定位事件链路，然后逐项验证增量发布与界面更新，最后确认所有思考文字都按顺序出现。";
  const observed = await page.locator("#app").evaluate(async (root, thinkingText) => {
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

    const values: string[] = [];
    const observer = new MutationObserver(() => {
      const value = document.querySelector<HTMLElement>(".thinking-panel__preview")?.textContent ?? "";
      if (value && values.at(-1) !== value) values.push(value);
    });
    observer.observe(document.body, { childList: true, characterData: true, subtree: true });

    const runId = "run-thinking-playback";
    const workspace = { workspace_id: "workspace-thinking", name: "Think playback", path: "F:/thinking", archived: false };
    state.workspace = workspace;
    state.workspaces = [workspace];
    state.sessions = [{
      session_id: "session-thinking", title: "Think playback", status: "active", updated_at: "",
      archived: false, pinned: false, workspace_id: "workspace-thinking",
      total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0,
    }];
    state.activeId = "session-thinking";
    state.timeline = new Map([[1, { step: 1, status: "thinking", tokens: [], toolCalls: [], runId }]]);
    state.activeRunId = runId;
    state.runActive = true;
    state.applyRuntimeEvent({ type: "llm.thinking", run_id: runId, step: 1, thinking: thinkingText });
    await Promise.resolve();
    state.applyRuntimeEvent({ type: "run.finished", run_id: runId, status: "success" });

    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => reject(new Error("Think playback did not finish")), 3000);
      const check = () => {
        const panel = document.querySelector<HTMLElement>(".thinking-panel");
        const value = panel?.querySelector<HTMLElement>(".thinking-panel__preview")?.textContent ?? "";
        if (value === thinkingText && panel?.dataset.state === "ok") {
          window.clearTimeout(timeout);
          resolve();
          return;
        }
        requestAnimationFrame(check);
      };
      requestAnimationFrame(check);
    });
    observer.disconnect();
    return values;
  }, target);

  expect(observed.length).toBeGreaterThan(3);
  expect(observed.at(-1)).toBe(target);
  expect(observed.every((value) => target.startsWith(value))).toBe(true);
  const lengths = observed.map((value) => Array.from(value).length);
  expect(lengths.every((length, index) => index === 0 || length > lengths[index - 1])).toBe(true);
  expect(Math.max(...lengths.map((length, index) => index === 0 ? length : length - lengths[index - 1]))).toBeLessThanOrEqual(12);
});

test("context injection expands to the complete live and restored text", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const liveTail = "LIVE_CONTEXT_TAIL";
  await page.locator("#app").evaluate((root, tail) => {
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

    const runId = "run-context-live";
    const workspace = { workspace_id: "workspace-context", name: "Context", path: "F:/context", archived: false };
    state.workspace = workspace;
    state.workspaces = [workspace];
    state.sessions = [{
      session_id: "session-context", title: "Context injection", status: "active", updated_at: "",
      archived: false, pinned: false, workspace_id: "workspace-context",
      total_input_tokens: 0, total_output_tokens: 0, total_elapsed_s: 0,
    }];
    state.activeId = "session-context";
    state.timeline = new Map([[1, {
      step: 1, status: "thinking", tokens: [], toolCalls: [], runId,
      userMessage: "检查上下文",
    }]]);
    state.activeRunId = runId;
    state.runActive = true;
    const text = `# Base context\n\n## Project Context\n${tail}`;
    state.applyRuntimeEvent({
      type: "context.injected", run_id: runId, source: "system", label: "上下文注入",
      chars: text.length, preview: "# Base context", text,
    });
  }, liveTail);

  const liveRow = page.locator(".context-injection-row");
  await expect(liveRow.getByText("上下文注入", { exact: true })).toBeVisible();
  await liveRow.getByRole("button").click();
  await expect(liveRow.locator("pre")).toContainText(liveTail);

  const restoredTail = "RESTORED_CONTEXT_TAIL";
  await page.locator("#app").evaluate((root, tail) => {
    const app = (root as HTMLElement & { __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } } }).__vue_app__;
    const state = app?._instance?.setupState as {
      hydrateTimeline: (
        messages: unknown[],
        runStats: Record<string, unknown>,
        contextInjections: Array<Record<string, unknown>>,
      ) => void;
    } | undefined;
    if (!state) throw new Error("Vue application state is unavailable");
    const text = `# Restored base\n\n## Session Notes\n${tail}`;
    state.hydrateTimeline(
      [
        { role: "user", content: "恢复历史", run_id: "run-context-history" },
        { role: "assistant", content: "历史回答", run_id: "run-context-history" },
      ],
      {},
      [{
        run_id: "run-context-history", source: "system", label: "上下文注入",
        chars: text.length, preview: "# Restored base", text,
      }],
    );
  }, restoredTail);

  const restoredRow = page.locator(".context-injection-row");
  await expect(restoredRow).toHaveCount(1);
  await restoredRow.getByRole("button").click();
  await expect(restoredRow.locator("pre")).toContainText(restoredTail);
});

test("high-risk permission dialog follows the dark theme", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("html").evaluate((root) => { root.dataset.appTheme = "dark"; });
  await page.waitForTimeout(180);
  await page.getByRole("button", { name: "标准审批", exact: true }).click();
  await page.getByRole("menuitemcheckbox", { name: /允许全部权限/ }).click();

  const dialog = page.getByRole("alertdialog", { name: "高风险权限提示" });
  await expect(dialog).toBeVisible();
  const theme = await dialog.evaluate((element) => {
    const style = (selector: string) => getComputedStyle(element.querySelector<HTMLElement>(selector)!);
    return {
      dialogBackground: getComputedStyle(element).backgroundColor,
      titleColor: style("h2").color,
      descriptionColor: style("header p").color,
      listColor: style(".permission-confirm__body ul").color,
      warningBackground: style(".permission-confirm__body > p").backgroundColor,
      warningColor: style(".permission-confirm__body > p").color,
      footerBackground: style("footer").backgroundColor,
      cancelBackground: style("footer button:not(.danger)").backgroundColor,
      cancelColor: style("footer button:not(.danger)").color,
    };
  });
  expect(theme).toEqual({
    dialogBackground: "rgb(32, 36, 37)",
    titleColor: "rgb(237, 240, 241)",
    descriptionColor: "rgb(168, 176, 179)",
    listColor: "rgb(168, 176, 179)",
    warningBackground: "rgb(63, 52, 36)",
    warningColor: "rgb(240, 194, 122)",
    footerBackground: "rgb(40, 45, 47)",
    cancelBackground: "rgb(43, 48, 50)",
    cancelColor: "rgb(237, 240, 241)",
  });
});

// 功能：验证右侧功能区"全屏"是真正的全屏——其余窗口功能全部隐藏，功能区独占整个视口，而非浮层遮挡
// 设计：复用 collapse 测试的 Vue 状态注入让会话区/功能区出现，点「全屏」后用 getBoundingClientRect 与 offsetParent
// 断言面板铺满视口且标题栏/导航/会话区真的 display:none，再按 Esc 验证恢复，避免只验证类名导致语义倒退
test("workspace panel fullscreen hides all other windows and fills the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("#app").evaluate((root) => {
    const app = (root as HTMLElement & { __vue_app__?: { _instance?: { setupState?: Record<string, unknown> } } }).__vue_app__;
    const state = app?._instance?.setupState;
    if (!state) throw new Error("Vue application state is unavailable");
    state.workspace = { workspace_id: "workspace-fixture", name: "Fixture", path: "F:/fixture", archived: false };
    state.sessions = [{ session_id: "session-fixture", title: "Fixture task", status: "active", updated_at: "", archived: false, pinned: false, workspace_id: "workspace-fixture" }];
    state.activeId = "session-fixture";
  });

  const inspector = page.locator(".project-inspector");
  const expandButton = page.getByRole("button", { name: "全屏", exact: true });
  await expect(expandButton).toBeVisible();
  await expandButton.click();
  await expect(inspector).toHaveClass(/is-expanded/);

  const geometry = await page.evaluate(() => {
    const panel = document.querySelector<HTMLElement>(".project-inspector.is-expanded")!;
    const rect = panel.getBoundingClientRect();
    return {
      panel: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      titlebarGone: !document.querySelector<HTMLElement>(".kimi-titlebar")?.offsetParent,
      sidebarGone: !document.querySelector<HTMLElement>(".sidebar-viewport")?.offsetParent,
      canvasGone: !document.querySelector<HTMLElement>(".task-canvas")?.offsetParent,
      dividerGone: !document.querySelector<HTMLElement>(".layout-divider")?.offsetParent,
      viewport: { width: window.innerWidth, height: window.innerHeight },
    };
  });

  expect(geometry.panel.x).toBe(0);
  expect(geometry.panel.y).toBe(0);
  expect(geometry.panel.width).toBeCloseTo(geometry.viewport.width, 0);
  expect(geometry.panel.height).toBeCloseTo(geometry.viewport.height, 0);
  expect(geometry.titlebarGone).toBe(true);
  expect(geometry.sidebarGone).toBe(true);
  expect(geometry.canvasGone).toBe(true);
  expect(geometry.dividerGone).toBe(true);

  // Esc 退出全屏：其余窗口功能恢复
  await page.keyboard.press("Escape");
  await expect(inspector).not.toHaveClass(/is-expanded/);
  await expect(page.locator(".kimi-titlebar")).toBeVisible();
  await expect(page.locator(".sidebar-viewport")).toBeVisible();
  await expect(page.locator(".task-canvas")).toBeVisible();
});

// 功能：模型管理页在窄窗口下不横向溢出、文字不重叠
// 设计：独立 fixture 挂载 ModelManager（IPC 已 mock），分别以 920px（宽）/620px（窄）两个视口渲染，
// 断言页面无横向滚动、操作列与按钮不重叠，并对窄视口提交视觉快照
async function openModelManagerFixture(page: import("@playwright/test").Page, width: number, height = 800) {
  await page.setViewportSize({ width, height });
  await page.goto("/tests/visual/fixtures/model-manager.html");
  await expect(page.getByRole("heading", { name: "模型", exact: true })).toBeVisible();
  // fixture 提供 3 个本地模型（mock 的 query_profile 服务端模型仅用于注入场景，不计入表格行）
  await expect(page.locator(".model-table-row")).toHaveCount(3);
}

test("model manager keeps a clear table layout at 920px and never overflows horizontally", async ({ page }) => {
  await openModelManagerFixture(page, 920);

  const geometry = await page.evaluate(() => {
    const body = document.querySelector<HTMLElement>(".model-manager-body")!;
    const table = document.querySelector<HTMLElement>(".model-table")!;
    const row = document.querySelector<HTMLElement>(".model-table-row")!;
    const action = row.querySelector<HTMLElement>("span:last-child")!;
    return {
      bodyScrollWidth: body.scrollWidth,
      bodyClientWidth: body.clientWidth,
      rowRight: row.getBoundingClientRect().right,
      tableRight: table.getBoundingClientRect().right,
      actionRight: action.getBoundingClientRect().right,
      headerVisible: !!Array.from(document.querySelectorAll(".model-table > header span")).find((el) => (el as HTMLElement).offsetParent),
      nameEllipsized: getComputedStyle(row.querySelector("b")!).textOverflow === "ellipsis",
    };
  });

  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.bodyClientWidth);
  expect(geometry.rowRight).toBeLessThanOrEqual(geometry.tableRight);
  expect(geometry.actionRight).toBeLessThanOrEqual(geometry.tableRight);
  expect(geometry.headerVisible).toBe(true);
  expect(geometry.nameEllipsized).toBe(true);

  // 920px 仍是完整表格：四列表头全部可见
  const headerLabels = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>(".model-table > header span"))
      .filter((el) => el.offsetParent)
      .map((el) => el.textContent?.trim()),
  );
  expect(headerLabels).toEqual(["模型", "服务商", "接口", "操作"]);
  await expect(page).toHaveScreenshot("model-manager-920.png", { fullPage: true });
});

test("model manager switches to single column at 620px without horizontal overflow", async ({ page }) => {
  await openModelManagerFixture(page, 620);

  const geometry = await page.evaluate(() => {
    const body = document.querySelector<HTMLElement>(".model-manager-body")!;
    const table = document.querySelector<HTMLElement>(".model-table")!;
    const rows = Array.from(document.querySelectorAll<HTMLElement>(".model-table-row"));
    const firstRow = rows[0]!;
    const header = document.querySelector<HTMLElement>(".model-table > header")!;
    const editorButton = document.querySelector<HTMLElement>(".model-add-button")!;
    const vendorCell = firstRow.querySelector<HTMLElement>(":scope > span:nth-child(2)")!;
    const apiCell = firstRow.querySelector<HTMLElement>(":scope > span:nth-child(3)")!;
    return {
      bodyScrollWidth: body.scrollWidth,
      bodyClientWidth: body.clientWidth,
      tableRight: table.getBoundingClientRect().right,
      bodyRight: body.getBoundingClientRect().right,
      firstRowRight: firstRow.getBoundingClientRect().right,
      editorButtonRight: editorButton.getBoundingClientRect().right,
      rowCount: rows.length,
      headerRight: header.getBoundingClientRect().right,
      vendorCellHidden: getComputedStyle(vendorCell).display === "none",
      apiCellHidden: getComputedStyle(apiCell).display === "none",
      nameTitle: firstRow.querySelector("b")!.getAttribute("title"),
      modelTitle: firstRow.querySelector("small")!.getAttribute("title"),
    };
  });

  expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.bodyClientWidth);
  expect(geometry.firstRowRight).toBeLessThanOrEqual(geometry.tableRight);
  expect(geometry.tableRight).toBeLessThanOrEqual(geometry.bodyRight);
  expect(geometry.editorButtonRight).toBeLessThanOrEqual(geometry.bodyRight);
  expect(geometry.headerRight).toBeLessThanOrEqual(geometry.bodyRight);
  expect(geometry.rowCount).toBe(3);
  // 窄窗口下服务商/接口列让位于名称与操作，完整值保留在 title 中
  expect(geometry.vendorCellHidden).toBe(true);
  expect(geometry.apiCellHidden).toBe(true);
  expect(geometry.nameTitle).toBeTruthy();
  expect(geometry.modelTitle).toBeTruthy();
  await expect(page).toHaveScreenshot("model-manager-620.png", { fullPage: true });
});

test("model editor form becomes single column at 620px and stays inside the dialog", async ({ page }) => {
  await openModelManagerFixture(page, 620);
  // 直接注入编辑器打开状态与服务商选择（绕过点击，避免 backdrop 拦截，与 diff-review 注入模式一致）
  await page.locator(".model-manager").evaluate((el) => {
    const instance = (el as HTMLElement & { __vueParentComponent?: { setupState?: Record<string, unknown> } }).__vueParentComponent;
    const setup = instance?.setupState;
    if (!setup) throw new Error("ModelManager setupState is unavailable");
    const apply = (key: string, value: unknown) => {
      const refish = setup[key] as { value?: unknown } | undefined;
      if (refish && typeof refish === "object" && "value" in refish) refish.value = value;
      else setup[key] = value;
    };
    apply("editorOpen", true);
    apply("selectedVendor", { name: "DeepSeek", logo: null, mark: "D", provider: "openai", baseUrl: "https://api.deepseek.com/v1", apiKeyUrl: "https://platform.deepseek.com/api_keys" });
  });
  await expect(page.locator(".model-editor-fields")).toBeVisible();

  const geometry = await page.evaluate(() => {
    const editor = document.querySelector<HTMLElement>(".model-editor")!;
    const fields = document.querySelector<HTMLElement>(".model-editor-fields")!;
    const grid = document.querySelector<HTMLElement>(".model-vendor-grid")!;
    const labels = Array.from(fields.querySelectorAll<HTMLElement>("label"));
    const editorRect = editor.getBoundingClientRect();
    const columns = getComputedStyle(fields).gridTemplateColumns.split(" ").length;
    const vendorColumns = getComputedStyle(grid).gridTemplateColumns.split(" ").length;
    return {
      editorWidth: editorRect.width,
      editorRight: editorRect.right,
      viewportWidth: window.innerWidth,
      fieldsColumns: columns,
      vendorColumns,
      fieldsInside: fields.getBoundingClientRect().right <= editorRect.right,
      labelCount: labels.length,
      labelsInside: labels.every((label) => label.getBoundingClientRect().right <= editorRect.right + 0.5),
    };
  });

  expect(geometry.editorWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.editorRight).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.fieldsColumns).toBe(1);
  expect(geometry.vendorColumns).toBe(1);
  expect(geometry.fieldsInside).toBe(true);
  expect(geometry.labelCount).toBeGreaterThan(0);
  expect(geometry.labelsInside).toBe(true);
  await expect(page.locator(".model-editor")).toHaveScreenshot("model-editor-620.png", { fullPage: true });
});

// 功能：模型管理页模态框的键盘与焦点交互（Issue #28）
// 设计：独立 fixture 挂载包装组件（触发按钮 + ModelManager），验证
// 初始焦点、Tab/Shift+Tab 焦点循环、Escape 分层关闭、关闭后焦点恢复。
async function openModelManagerKeyboard(page: import("@playwright/test").Page, width = 920, height = 800) {
  await page.setViewportSize({ width, height });
  await page.goto("/tests/visual/fixtures/model-manager-keyboard.html");
  await expect(page.locator("#open-model-manager")).toBeVisible();
  await page.locator("#open-model-manager").click();
  await expect(page.getByRole("heading", { name: "模型", exact: true })).toBeVisible();
  await expect(page.locator(".model-table-row")).toHaveCount(3);
}

test("model manager dialog receives initial focus and restores focus to the trigger on close", async ({ page }) => {
  await openModelManagerKeyboard(page);
  // 初始焦点应在模型管理面板内，而不是停留在触发按钮或 body
  const initialFocusInside = await page.locator(".model-manager").evaluate((el) =>
    el.contains(document.activeElement),
  );
  expect(initialFocusInside).toBe(true);

  // 关闭模型管理（点击关闭按钮），焦点应回到触发按钮
  await page.getByRole("button", { name: "关闭模型管理", exact: true }).click();
  await expect(page.locator(".model-manager")).not.toBeVisible();
  await expect(page.locator("#open-model-manager")).toBeFocused();
});

test("model manager editor dialog traps Tab focus and closes with Escape", async ({ page }) => {
  await openModelManagerKeyboard(page);
  // 通过注入打开编辑器（绕过 backdrop 点击拦截，与既有测试一致）
  await page.locator(".model-manager").evaluate((el) => {
    const instance = (el as HTMLElement & { __vueParentComponent?: { setupState?: Record<string, unknown> } }).__vueParentComponent;
    const setup = instance?.setupState;
    if (!setup) throw new Error("ModelManager setupState is unavailable");
    const apply = (key: string, value: unknown) => {
      const refish = setup[key] as { value?: unknown } | undefined;
      if (refish && typeof refish === "object" && "value" in refish) refish.value = value;
      else setup[key] = value;
    };
    apply("editorOpen", true);
    apply("selectedVendor", { name: "DeepSeek", logo: null, mark: "D", provider: "openai", baseUrl: "https://api.deepseek.com/v1", apiKeyUrl: "https://platform.deepseek.com/api_keys" });
  });
  const editor = page.locator(".model-editor");
  await expect(editor).toBeVisible();

  // 初始焦点应在编辑器内（首个可聚焦控件）
  const firstFocusable = editor.locator("button, input, select, textarea").first();
  await expect(firstFocusable).toBeFocused();

  // Tab 循环：在编辑器内连续 Tab，焦点始终不离开编辑器
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("Tab");
    const stillInside = await editor.evaluate((el) => el.contains(document.activeElement));
    expect(stillInside).toBe(true);
  }

  // Shift+Tab 反向循环，焦点仍不离开编辑器
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Shift+Tab");
  const insideAfterShiftTab = await editor.evaluate((el) => el.contains(document.activeElement));
  expect(insideAfterShiftTab).toBe(true);

  // Escape 关闭编辑器，且模型管理面板仍打开
  await page.keyboard.press("Escape");
  await expect(editor).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "模型", exact: true })).toBeVisible();
});

test("model delete dialog closes with Escape and restores focus to the delete button", async ({ page }) => {
  await openModelManagerKeyboard(page);
  // 打开删除弹窗（点击自定义模型的删除按钮）
  const deleteButton = page.locator(".model-table-row").filter({ hasText: "自定义模型" }).getByRole("button", { name: /删除/ });
  await deleteButton.click();
  await expect(page.getByRole("alertdialog", { name: "删除模型" })).toBeVisible();
  await expect(page.getByRole("button", { name: "取消", exact: true })).toBeFocused();

  // Escape 关闭删除弹窗
  await page.keyboard.press("Escape");
  await expect(page.getByRole("alertdialog", { name: "删除模型" })).not.toBeVisible();
  // 焦点应回到删除按钮
  await expect(deleteButton).toBeFocused();
});

test("Escape closes only the topmost dialog, a second Escape closes the manager", async ({ page }) => {
  await openModelManagerKeyboard(page);
  // 打开编辑器（第一层弹窗）
  await page.locator(".model-manager").evaluate((el) => {
    const instance = (el as HTMLElement & { __vueParentComponent?: { setupState?: Record<string, unknown> } }).__vueParentComponent;
    const setup = instance?.setupState;
    if (!setup) throw new Error("ModelManager setupState is unavailable");
    const apply = (key: string, value: unknown) => {
      const refish = setup[key] as { value?: unknown } | undefined;
      if (refish && typeof refish === "object" && "value" in refish) refish.value = value;
      else setup[key] = value;
    };
    apply("editorOpen", true);
    apply("selectedVendor", { name: "DeepSeek", logo: null, mark: "D", provider: "openai", baseUrl: "https://api.deepseek.com/v1", apiKeyUrl: "https://platform.deepseek.com/api_keys" });
  });
  const editor = page.locator(".model-editor");
  await expect(editor).toBeVisible();

  // 第一次 Escape：只关闭编辑器，模型管理面板仍打开
  await page.keyboard.press("Escape");
  await expect(editor).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "模型", exact: true })).toBeVisible();

  // 第二次 Escape：关闭模型管理面板，焦点回到触发按钮
  await page.keyboard.press("Escape");
  await expect(page.locator(".model-manager")).not.toBeVisible();
  await expect(page.locator("#open-model-manager")).toBeFocused();
});

