import { createApp, defineComponent, h } from "vue";
import ExecutionTimeline from "../../../src/components/timeline/ExecutionTimeline.vue";
import type { TimelineStep } from "../../../src/components/timeline/types";
import { i18n } from "../../../src/i18n";
import "../../../src/kimi.css";
import "../../../src/timeline.css";
import "../../../src/workbench.css";

const steps: TimelineStep[] = [
  {
    step: 1,
    runId: "run-complete",
    status: "done",
    userMessage: "修复登录超时后重复跳转的问题，并补充回归测试",
    tokens: [],
    toolCalls: [
      { id: "read", name: "grep_search", params: { query: "session expired" }, status: "done", elapsedMs: 180 },
      { id: "edit", name: "edit_file", params: { path: "src/auth/session.ts", description: "修正超时跳转条件" }, status: "done", elapsedMs: 90 },
      { id: "test", name: "bash", params: { command: "npm test -- auth" }, status: "done", elapsedMs: 1840, output: "12 tests passed" },
    ],
    events: [
      { id: "intro", kind: "text", text: "我先检查了登录拦截器和路由守卫的职责边界。" },
      { id: "thinking", kind: "thinking", text: "重复跳转来自请求拦截器和路由守卫同时处理过期状态。" },
      { id: "read", kind: "tool", toolCallId: "read" },
      { id: "edit", kind: "tool", toolCallId: "edit" },
      { id: "test", kind: "tool", toolCallId: "test" },
      { id: "summary", kind: "text", text: "我修复了登录超时后的重复跳转：请求拦截器现在只负责清理会话，页面跳转统一由路由守卫处理。\n\n同时补充了重复响应与返回登录页两种回归场景。" },
    ],
    thinking: "重复跳转来自请求拦截器和路由守卫同时处理过期状态。保留路由守卫作为唯一跳转入口。",
    finalText: "我修复了登录超时后的重复跳转：请求拦截器现在只负责清理会话，页面跳转统一由路由守卫处理。\n\n同时补充了重复响应与返回登录页两种回归场景。",
    runStats: { inputTokens: 12840, outputTokens: 1630, cacheReadInputTokens: 9340, elapsedSeconds: 78.4 },
    plan: [
      { id: 1, subject: "定位重复跳转入口", status: "completed", blocked_by: [] },
      { id: 2, subject: "统一过期会话处理", status: "completed", blocked_by: [1] },
      { id: 3, subject: "补充回归测试", status: "completed", blocked_by: [2] },
    ],
    tests: [{ status: "passed", summary: "认证相关测试 12/12 通过" }],
    changes: [{ paths: ["src/auth/session.ts", "src/router/guard.ts", "tests/auth/session.test.ts"], workspacePath: "F:/project" }],
  },
  {
    step: 2,
    runId: "run-recovered",
    status: "done",
    userMessage: "先尝试一个可能失败的命令，失败后换方案继续",
    tokens: [],
    toolCalls: [
      { id: "bad", name: "bash", params: { command: "npm run missing" }, status: "failed", error: "missing script" },
      { id: "ok", name: "bash", params: { command: "npm test -- auth" }, status: "done", output: "12 tests passed" },
    ],
    finalText: "第一次命令不可用，我已切换到项目中存在的测试入口并完成验证。",
    runStats: { inputTokens: 4280, outputTokens: 612, cacheReadInputTokens: 3200, elapsedSeconds: 18.7 },
    tests: [{ status: "passed", summary: "认证相关测试 12/12 通过" }],
    outcome: { status: "success" },
  },
  {
    step: 3,
    runId: "run-waiting",
    status: "acting",
    userMessage: "安装缺少的依赖并继续验证",
    tokens: [],
    toolCalls: [{ id: "permission", name: "bash", params: { command: "npm install" }, status: "awaiting_permission" }],
    permission: { toolUseId: "permission", toolName: "运行安装命令", preview: "npm install", status: "pending" },
  },
  {
    step: 4,
    runId: "run-active",
    status: "acting",
    userMessage: "检查剩余的类型错误",
    runStartedAt: new Date(Date.now() - 12_000).toISOString(),
    runStats: { inputTokens: 2840, outputTokens: 476, cacheReadInputTokens: 2100, elapsedSeconds: 0 },
    tokens: [],
    toolCalls: [{ id: "search", name: "grep_search", params: { query: "TypeError" }, status: "running" }],
    plan: [
      { id: 1, subject: "收集类型检查结果", status: "completed", blocked_by: [] },
      { id: 2, subject: "定位剩余错误", status: "in_progress", blocked_by: [1] },
      { id: 3, subject: "运行完整验证", status: "pending", blocked_by: [2] },
    ],
  },
];

const Fixture = defineComponent({
  setup: () => () => h("main", { class: "fixture-shell" }, [
    h("header", [h("span", "SztuCode"), h("b", "修复认证流程"), h("small", "本地工作区")]),
    h("section", { class: "fixture-stream" }, [h(ExecutionTimeline, { steps })]),
    h("footer", "描述下一步工作..."),
  ]),
});

createApp(Fixture).use(i18n).mount("#app");
