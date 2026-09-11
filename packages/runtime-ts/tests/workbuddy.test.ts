import assert from "node:assert/strict";
import test from "node:test";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { buildSystemPrompt, buildDynamicContext, loadAgentProfile } from "../src/prompt-loader.js";
import { loadWorkbuddyResource, readPromptResource, renderWorkbuddyText, resourcePath, workbuddyManifest, workbuddyMode } from "../src/workbuddy-resources.js";
import { SkillLoader } from "../src/skills.js";
import { PluginManager } from "../src/plugins.js";
import { SubagentManager } from "../src/subagent.js";
import { EventBus } from "../src/event-bus.js";
import { PermissionManager } from "../src/permissions.js";
import { JsonlSessionBackend } from "@sztucode/session-fs";
import { RunManager } from "../src/run-manager.js";
import { runMemoryEvolution } from "../src/memory-evolution.js";

test("WorkBuddy bundle is complete and every product template renders", async () => {
  const manifest = workbuddyManifest();
  assert.equal(manifest.files.length, 485);
  assert.equal(manifest.skills.length, 48);
  assert.equal(manifest.agents.length, 19);
  for (const file of manifest.files) {
    const bytes = await readFile(resourcePath(file.path));
    assert.equal(createHash("sha256").update(bytes).digest("hex"), file.sha256, file.path);
    if (file.path.endsWith(".tpl") || file.path.startsWith("modes/") && file.path.endsWith(".md")) {
      const text = loadWorkbuddyResource(file.path);
      assert.doesNotMatch(text, /\{%|\{\{/, file.path);
    }
  }
  for (const mode of ["ask", "craft", "plan", "expert"] as const) assert.ok(workbuddyMode(mode));
  assert.equal(renderWorkbuddyText("{{productName}} {{values.join(',')}} {% if values.length === 2 %}yes{% endif %}", { values: ["a", "b"] }), "SztuCode a,b yes");
  const summary = loadWorkbuddyResource("product/context-summary-prompt.tpl");
  assert.doesNotMatch(summary, /All tasks described below are already completed/);
  assert.match(summary, /Never mark unfinished work completed/);
});

test("resource reader is bounded and cannot escape the installed bundle", () => {
  const first = JSON.parse(readPromptResource("product/", 0, 3));
  const second = JSON.parse(readPromptResource("product/", first.next_offset, 3));
  assert.equal(first.total_files, 118);
  assert.equal(first.files.length, 3);
  assert.notDeepEqual(first.files, second.files);
  const excerpt = JSON.parse(readPromptResource("product/command-commit-prompt.tpl", 2, 4));
  assert.equal(excerpt.text.split("\n").length, 4);
  assert.equal(excerpt.next_offset, 6);
  for (const value of ["../main/index.json", "../../", resourcePath("manifest.json")]) assert.throws(() => readPromptResource(value), /relative|traversal|escapes/);
  assert.throws(() => readPromptResource("", 0, 1001), /pagination/);
});

test("nested skills and plugins support lazy loading, disable and project overrides", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-workbuddy-"));
  try {
    const config = path.join(root, "config");
    const loader = new SkillLoader(root, config);
    const items = await loader.list();
    for (const skill of workbuddyManifest().skills) {
      const loaded = await loader.get(skill.name);
      assert.equal(loaded.source, "workbuddy");
      assert.match(loaded.system_prompt_template, /Skill directory: skills\//);
      assert.match(loaded.system_prompt_template, /# SztuCode runtime contract/);
    }
    for (const command of workbuddyManifest().commands) {
      const loaded = await loader.get(command.name);
      assert.equal(loaded.allow_implicit_invocation, false);
      assert.doesNotMatch(loaded.system_prompt_template, /\{\{|\{%/);
    }
    const nested = items.find(item => item.source === "workbuddy" && item.plugin)!;
    const plugins = new PluginManager(root, config);
    await plugins.setEnabled(`builtin:${nested.plugin}`, false);
    await assert.rejects(loader.get(nested.name), /disabled/);
    await plugins.setEnabled(`builtin:${nested.plugin}`, true);
    await loader.setEnabled(nested.id, false);
    await assert.rejects(loader.get(nested.name), /disabled/);
    await loader.setEnabled(nested.id, true);
    assert.match((await loader.get(nested.name)).system_prompt_template, /runtime contract/);
    const local = path.join(root, ".sztu", "skills", nested.name);
    await mkdir(local, { recursive: true });
    await writeFile(path.join(local, "SKILL.md"), `---\nname: ${nested.name}\nworkbuddy: true\ndescription: Local\n---\nKeep {{ literal }} in code examples.\n`);
    assert.equal((await loader.get(nested.name)).source, "project");
    assert.match((await loader.get(nested.name)).system_prompt_template, /\{\{ literal \}\}/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("imported agent instructions are system messages and empty tool lists stay empty", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-workbuddy-agent-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    for (const agent of workbuddyManifest().agents) {
      const profile = await loadAgentProfile(root, agent.name);
      assert.match(profile.systemPrompt, /SztuCode runtime contract/);
      assert.doesNotMatch(profile.systemPrompt, /\{\{|\{%/);
    }
    const injected: string[] = [];
    events.subscribe(event => { if (event.type === "context.injected") injected.push(event.text ?? ""); });
    const agent = workbuddyManifest().agents.find(item => item.tools.length === 0)!;
    assert.ok(agent);
    const permissions = new PermissionManager(events, 20);
    const manager = new SubagentManager({ complete: async (messages, tools) => {
      assert.equal(messages[0].role, "system");
      assert.equal(messages[0].content, injected.at(-1));
      assert.match(String(messages[0].content), /SztuCode runtime contract/);
      assert.equal(tools.list().length, 0);
      assert.doesNotMatch(String(messages.at(-1)?.content), /# Role instructions/);
      return { text: "done", tool_calls: [], stop_reason: "end_turn" };
    } }, root, events, permissions, new JsonlSessionBackend(path.join(root, "sessions")));
    await manager.run(agent.name, "Summarize the supplied task.");
    assert.equal(injected.length, 1);
    const base = await buildSystemPrompt(root);
    assert.doesNotMatch(base, /\{\{|\{%/);
    assert.match(await buildDynamicContext(root), /# Available skills/);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }); }
});

test("active command instructions are included in the displayed main system prompt", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-workbuddy-command-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  let injected = "";
  try {
    events.subscribe(event => { if (event.type === "context.injected") injected = event.text ?? ""; });
    const manager = new RunManager(events, { complete: async messages => {
      if (String(messages[0]?.content).includes("[memory-evolution]")) return { text: "[]", tool_calls: [], stop_reason: "end_turn" };
      assert.equal(messages.filter(message => message.role === "system").length, 1);
      assert.equal(messages[0].content, injected);
      assert.match(injected, /ACTIVE_COMMAND_SENTINEL/);
      return { text: "done", tool_calls: [], stop_reason: "end_turn" };
    } }, root);
    await new Promise<void>((resolve, reject) => {
      const unsubscribe = events.subscribe(event => {
        if (event.type === "run.finished") { unsubscribe(); event.status === "success" ? resolve() : reject(new Error(event.reason)); }
      });
      manager.start("inspect", [{ role: "system", content: "ACTIVE_COMMAND_SENTINEL" }], undefined, root);
    });
    let called = false;
    await runMemoryEvolution({ complete: async messages => {
      called = true;
      assert.equal(messages[0].role, "system");
      assert.match(String(messages[0].content), /friction points/);
      assert.match(String(messages[0].content), /targetNote/);
      return { text: "[]", tool_calls: [], stop_reason: "end_turn" };
    } }, [], path.join(root, "memory"));
    assert.ok(called);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }); }
});
