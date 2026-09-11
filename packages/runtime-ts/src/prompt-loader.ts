import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";
import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { PermissionMode } from "@sztucode/protocol";
import { composeRuntimePrompt, dynamicRuntimePromptEntries, type PromptRuntimeContext } from "./prompt-harness.js";
import type { ChatMessage } from "./agent-loop.js";
import { SkillLoader } from "./skills.js";

const execFileAsync = promisify(execFile);
const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
const runtimeRoot = existsSync(path.join(moduleDirectory, "prompts")) ? moduleDirectory : path.resolve(moduleDirectory, "..");
const promptRoot = path.join(runtimeRoot, "prompts", "content");
const agentRoot = path.join(runtimeRoot, "agents", "builtin");
const instructionNames = ["AGENT.md", "AGENTS.md", "CLAUDE.md", "SZTUCODE.md", "CLAW.md"];

function stripHtmlComments(text: string): string {
  return text.replace(/<!--[\s\S]*?-->/g, "").replace(/^\s*\n/gm, "").trim();
}

export type AgentProfile = { name: string; description: string; systemPrompt: string; allowedTools: string[] | null; permissionMode: PermissionMode | null; maxSteps: number };

async function markdownGroup(group: string): Promise<string[]> {
  const root = path.join(promptRoot, group);
  try {
    const entries = (await readdir(root, { withFileTypes: true })).filter((entry) => entry.isFile() && entry.name.endsWith(".md")).sort((a, b) => a.name.localeCompare(b.name));
    return Promise.all(entries.map(async (entry) => stripHtmlComments(await readFile(path.join(root, entry.name), "utf8"))));
  } catch { return []; }
}

async function firstPrompt(group: string, fragment: string): Promise<string> {
  const root = path.join(promptRoot, group);
  try {
    const name = (await readdir(root)).find((entry) => entry.endsWith(".md") && entry.includes(fragment));
    return name ? stripHtmlComments(await readFile(path.join(root, name), "utf8")) : "";
  } catch { return ""; }
}

async function gitSnapshot(root: string): Promise<string> {
  try {
    const result = await execFileAsync("git", ["-C", root, "status", "--short", "--branch"], { timeout: 10_000, maxBuffer: 20_000 });
    return result.stdout.trim();
  } catch { return ""; }
}

async function projectInstructions(root: string): Promise<string> {
  const parts: string[] = [];
  let current = path.resolve(root);
  for (let depth = 0; depth < 6; depth += 1) {
    for (const name of instructionNames) {
      const file = path.join(current, name);
      try {
        const info = await stat(file);
        if (!info.isFile()) continue;
        const text = (await readFile(file, "utf8")).trim();
        if (text) parts.push(`## ${name}\n${text.slice(0, 4_000)}`);
      } catch { /* optional instruction */ }
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return parts.join("\n\n").slice(0, 12_000);
}

// 进程级 system prompt memo：跨 run 复用拼接结果。静态层字节只由 role、tool 集合与
// prompt 文件内容决定（permissionMode/memoryEnabled 走 dynamic 层），key 按此收敛；
// tool 集合排序去重，MCP 异步注册只改变集合成员时才产生新 key。
const systemPromptMemo = new Map<string, Promise<string>>();
const SYSTEM_PROMPT_MEMO_LIMIT = 16;

export async function buildSystemPrompt(workspaceRoot: string, role = "coder", runtime: PromptRuntimeContext = {}): Promise<string> {
  const memoKey = JSON.stringify([role, [...new Set(runtime.toolNames ?? [])].sort()]);
  const memoized = systemPromptMemo.get(memoKey);
  if (memoized) return memoized;
  const building = (async () => {
    const sections = [
      ...(await markdownGroup("main")),
      await firstPrompt("safety-prompts", "malicious-code-protection"),
      await firstPrompt("doing-tasks", "software-engineering-focus"),
      await firstPrompt("doing-tasks", "read-before-modifying"),
      await firstPrompt("doing-tasks", "security"),
      await firstPrompt("doing-tasks", "blocked-approach"),
      ...(await markdownGroup("output-efficiency")),
      await firstPrompt("tone-and-style", "concise-output-short"),
      `# Runtime context\n- Agent role: ${role}`,
    ].filter(Boolean);
    return composeRuntimePrompt(sections.join("\n\n"), runtime);
  })();
  systemPromptMemo.set(memoKey, building);
  // 拼接失败（prompt 文件损坏等）不落缓存，下一次调用重新构建。
  building.catch(() => systemPromptMemo.delete(memoKey));
  if (systemPromptMemo.size > SYSTEM_PROMPT_MEMO_LIMIT) {
    const oldest = systemPromptMemo.keys().next().value;
    if (oldest !== undefined && oldest !== memoKey) systemPromptMemo.delete(oldest);
  }
  return building;
}

// 工作区事实（instructions/skills/git status）中 gitSnapshot 是一次子进程调用（沙箱/冷盘下
// 可达秒级）。按 root 做 in-flight 去重：同一时刻发起的并发调用共享同一次构建（workflow DAG
// 同时派发的多个子代理只跑一次 git），构建完成后即失效，后续调用总是读到最新工作区状态，
// 不引入跨 run 的陈旧性（byte-stable 契约要求编辑后重建立即反映新内容）。
type WorkspaceFacts = { instructions: string; skills: Array<{ name: string; description?: string }>; git: string };
const workspaceFactsInFlight = new Map<string, Promise<WorkspaceFacts>>();

function workspaceFacts(root: string): Promise<WorkspaceFacts> {
  const existing = workspaceFactsInFlight.get(root);
  if (existing) return existing;
  const value = (async (): Promise<WorkspaceFacts> => {
    const instructions = await projectInstructions(root);
    let skills: WorkspaceFacts["skills"] = [];
    try { skills = (await new SkillLoader(root).list()).filter((skill) => skill.enabled); } catch { /* optional skill roots */ }
    const git = await gitSnapshot(root);
    return { instructions, skills, git };
  })();
  workspaceFactsInFlight.set(root, value);
  value.then(() => undefined, () => undefined).then(() => { if (workspaceFactsInFlight.get(root) === value) workspaceFactsInFlight.delete(root); });
  return value;
}

/** Render once per run, then persist with the goal so history stays append-only. */
export async function buildDynamicContext(workspaceRoot: string, runtime: PromptRuntimeContext = {}, snapshots: string[] = []): Promise<string> {
  const sections = [`- Working directory: ${path.resolve(workspaceRoot)}\n- Date: ${new Date().toISOString().slice(0, 10)}`];
  const { instructions, skills, git } = await workspaceFacts(workspaceRoot);
  if (instructions) sections.push(`# Project instructions\n${instructions}`);
  if (skills.length) sections.push(`# Available skills\n${skills.map((skill) => `- ${skill.name}: ${skill.description || "No description"}`).join("\n")}\nUse the skill tool to load full instructions when a skill is relevant.`);
  if (git) sections.push(`Current git status snapshot:\n${git}`);
  sections.push(...await dynamicRuntimePromptEntries(runtime), ...snapshots);
  return `<system-reminder>\n${sections.filter(Boolean).join("\n\n")}\n</system-reminder>`;
}

export function appendGoalReminder(content: ChatMessage["content"], reminder: string): ChatMessage["content"] {
  if (!reminder) return content;
  return typeof content === "string" ? `${content}\n\n${reminder}` : [...content, { type: "text", text: reminder }];
}

function parseTomlProfile(text: string, name: string): AgentProfile {
  const description = text.match(/^description\s*=\s*["']([^"']*)["']/m)?.[1] ?? `${name} agent`;
  const promptId = text.match(/^prompt_id\s*=\s*["']([^"']*)["']/m)?.[1] ?? "";
  const parsedMode = text.match(/^permission_mode\s*=\s*["']([^"']*)["']/m)?.[1];
  const permissionMode: PermissionMode | null = parsedMode && ["normal", "plan", "accept_edits", "auto"].includes(parsedMode) ? parsedMode as PermissionMode : null;
  const maxSteps = Number(text.match(/^max_steps\s*=\s*(\d+)/m)?.[1] ?? 20);
  const allowedMatch = text.match(/^allowed_tools\s*=\s*\[([\s\S]*?)\]/m);
  const allowedTools = allowedMatch ? [...allowedMatch[1].matchAll(/["']([^"']+)["']/g)].map((match) => match[1]) : null;
  const inlinePrompt = text.match(/system_prompt\s*=\s*"""([\s\S]*?)"""/)?.[1]?.trim() ?? "";
  return { name, description, systemPrompt: promptId || inlinePrompt, allowedTools, permissionMode, maxSteps };
}

export async function loadAgentProfile(workspaceRoot: string, name: string): Promise<AgentProfile> {
  const candidates = [path.join(workspaceRoot, ".sztu", "agents", `${name}.toml`), path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu", "agents", `${name}.toml`), path.join(agentRoot, `${name}.toml`)];
  for (const file of candidates) {
    try {
      const profile = parseTomlProfile(await readFile(file, "utf8"), name);
      if (profile.systemPrompt) {
        const promptFile = path.join(promptRoot, "subagent-prompts", `agent-prompt-${profile.systemPrompt}.md`);
        try { profile.systemPrompt = stripHtmlComments(await readFile(promptFile, "utf8")); } catch { /* inline/system prompt fallback */ }
      }
      return profile;
    } catch { /* try lower-priority profile */ }
  }
  return { name, description: `${name} agent`, systemPrompt: "", allowedTools: null, permissionMode: null, maxSteps: 20 };
}
