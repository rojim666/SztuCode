import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { SettingsStore } from "../src/settings.js";
import { ModelProfileStore } from "../src/model-profiles.js";
import { probeModel, validateSetting } from "../src/server-helpers.js";
import { OpenAiCompatibleProvider } from "../src/providers/openai.js";
import { AnthropicMessagesProvider } from "../src/providers/anthropic.js";
import { ToolRegistry } from "../src/tools.js";

test("reasoning effort persists per profile and rejects invalid values before mutation", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-reasoning-"));
  try {
    const settingsFile = path.join(root, "settings.json");
    const profilesFile = path.join(root, "models.json");
    const settings = new SettingsStore(settingsFile);
    const models = new ModelProfileStore(settings, profilesFile);
    const base = { vendor: "test", provider: "openai" as const, model: "test-model", base_url: "" };
    await models.save({ ...base, id: "deep", name: "Deep", reasoning_effort: "high" });
    await models.save({ ...base, id: "fast", name: "Fast", reasoning_effort: "low" });
    assert.equal((await models.select("deep")).reasoning_effort, "high");
    const reopened = new ModelProfileStore(new SettingsStore(settingsFile), profilesFile);
    assert.equal((await reopened.select("fast")).reasoning_effort, "low");
    await reopened.save({ ...base, id: "fast", name: "Fast", reasoning_effort: "" });
    assert.equal((await new SettingsStore(settingsFile).get()).reasoning_effort, "");
    await assert.rejects(models.save({ ...base, id: "deep", name: "Invalid", reasoning_effort: "invalid", select: false }), /reasoning_effort must/);
    assert.equal((await models.list()).find(p => p.id === "deep")?.name, "Deep");
    await assert.rejects(settings.update({ reasoning_effort: "invalid" }), /reasoning_effort must/);
    assert.equal((await settings.get()).reasoning_effort, "high");
    assert.throws(() => validateSetting("reasoning_effort", null), /reasoning_effort must/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("OpenAI probes and runs transmit effort in the correct API field and omit defaults", async () => {
  const originalFetch = globalThis.fetch;
  const bodies: Record<string, unknown>[] = [];
  globalThis.fetch = async (_url, init) => {
    bodies.push(JSON.parse(String(init?.body)));
    return Response.json({ choices: [{ message: { content: "OK" }, finish_reason: "stop" }], output_text: "OK", usage: {} });
  };
  try {
    for (const apiFormat of ["openai_chat_completions", "openai_responses"] as const) {
      for (const effort of ["", "low", "medium", "high", "xhigh", "max"]) {
        const result = await probeModel({ model: "test", api_format: apiFormat, reasoning_effort: effort });
        assert.equal(result.success, true);
        await new OpenAiCompatibleProvider({ apiKey: "test", model: "test", apiFormat, reasoningEffort: effort, temperature: 0.4, topP: 0.9 }).complete([{ role: "user", content: "hi" }], new ToolRegistry());
        const [probe, run] = bodies.slice(-2);
        for (const body of [probe, run]) {
          assert.deepEqual(body.reasoning, effort && apiFormat === "openai_responses" ? { effort, summary: "auto" } : undefined);
          assert.equal(body.reasoning_effort, effort && apiFormat === "openai_chat_completions" ? effort : undefined);
        }
        assert.equal(run.temperature, effort ? undefined : 0.4);
        assert.equal(run.top_p, effort ? undefined : 0.9);
      }
    }
    const before = bodies.length;
    await assert.rejects(probeModel({ model: "test", reasoning_effort: "invalid" }), /reasoning_effort must/);
    assert.equal(bodies.length, before);
  } finally { globalThis.fetch = originalFetch; }
});

test("Anthropic probes and runs use increasing budgets including xhigh and max", async () => {
  const originalFetch = globalThis.fetch;
  const bodies: Record<string, any>[] = [];
  globalThis.fetch = async (_url, init) => {
    bodies.push(JSON.parse(String(init?.body)));
    return Response.json({ content: [{ type: "text", text: "OK" }], stop_reason: "end_turn" });
  };
  try {
    for (const [effort, budget] of [["", 0], ["low", 2048], ["medium", 8192], ["high", 24576], ["xhigh", 32768], ["max", 65536]] as const) {
      assert.equal((await probeModel({ model: "test", api_format: "anthropic_messages", reasoning_effort: effort, max_output_tokens: 8192 })).success, true);
      await new AnthropicMessagesProvider({ apiKey: "test", model: "test", reasoningEffort: effort, maxTokens: 8192, temperature: 0.4, topP: 0.9 }).complete([{ role: "user", content: "hi" }], new ToolRegistry());
      const [probe, run] = bodies.slice(-2);
      for (const body of [probe, run]) {
        assert.deepEqual(body.thinking, effort ? { type: "enabled", budget_tokens: budget } : undefined);
        if (effort) assert.ok(body.max_tokens > budget);
      }
      assert.equal(run.temperature, effort ? undefined : 0.4);
      assert.equal(run.top_p, effort ? undefined : 0.9);
    }
  } finally { globalThis.fetch = originalFetch; }
});
