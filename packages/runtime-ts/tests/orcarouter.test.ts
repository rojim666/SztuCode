import assert from "node:assert/strict";
import test from "node:test";
import { ToolRegistry } from "../src/tools.js";
import { ORCAROUTER_BASE_URL, OrcaRouterProvider, type OrcaRouterProviderOptions, bareModelId, isOrcaRouterUrl, rejectsTemperature, rejectsTopP } from "../src/providers/orcarouter.js";

type Captured = { url: string; headers: Headers; body: Record<string, any> };

async function callOrca(options: OrcaRouterProviderOptions): Promise<Captured> {
  const originalFetch = globalThis.fetch;
  let captured: Captured = { url: "", headers: new Headers(), body: {} };
  globalThis.fetch = (async (input, init) => {
    captured = { url: String(input), headers: new Headers(init?.headers), body: JSON.parse(String(init?.body)) as Record<string, any> };
    return new Response(JSON.stringify({ choices: [{ message: { content: "ok" } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    const tools = new ToolRegistry();
    tools.register({ name: "read_file", description: "read", permission: "read_only", schema: { type: "object" }, invoke: async () => ({ ok: true, output: "" }) });
    await new OrcaRouterProvider(options).complete([{ role: "system", content: "stable" }, { role: "user", content: "hi" }], tools);
  } finally { globalThis.fetch = originalFetch; }
  return captured;
}

test("OrcaRouter provider defaults to the gateway URL and sends attribution headers", async () => {
  const { url, headers } = await callOrca({ apiKey: "sk-orca-test", model: "deepseek/deepseek-v4-flash" });
  assert.equal(url, `${ORCAROUTER_BASE_URL}/chat/completions`);
  assert.equal(headers.get("authorization"), "Bearer sk-orca-test");
  assert.equal(headers.get("HTTP-Referer"), "https://github.com/rojim666/SztuCode");
  assert.equal(headers.get("X-Title"), "SztuCode");
});

test("OrcaRouter provider drops temperature for models that reject it", async () => {
  const { body } = await callOrca({ apiKey: "sk-orca-test", model: "openai/gpt-5.4", temperature: 0.3, topP: 0.9 });
  assert.equal(body.temperature, undefined);
  assert.equal(body.top_p, 0.9);
});

test("OrcaRouter provider drops both sampling params for Kimi K3", async () => {
  const { body } = await callOrca({ apiKey: "sk-orca-test", model: "kimi/kimi-k3", temperature: 0.3, topP: 0.9 });
  assert.equal(body.temperature, undefined);
  assert.equal(body.top_p, undefined);
});

test("OrcaRouter provider keeps sampling params for models that accept them", async () => {
  const { body } = await callOrca({ apiKey: "sk-orca-test", model: "deepseek/deepseek-v4-flash", temperature: 0.3, topP: 0.9 });
  assert.equal(body.temperature, 0.3);
  assert.equal(body.top_p, 0.9);
});

test("OrcaRouter provider only sends cache_control to Anthropic upstreams", async () => {
  const anthropic = await callOrca({ apiKey: "sk-orca-test", model: "anthropic/claude-sonnet-4.6", cacheControl: true });
  assert.deepEqual(anthropic.body.messages[0].cache_control, { type: "ephemeral" });
  assert.deepEqual(anthropic.body.tools[0].cache_control, { type: "ephemeral" });

  const openai = await callOrca({ apiKey: "sk-orca-test", model: "openai/gpt-5.6-terra", cacheControl: true });
  assert.equal(openai.body.messages[0].cache_control, undefined);
  assert.equal(openai.body.tools[0].cache_control, undefined);
});

test("OrcaRouter provider forwards an explicit fallback chain", async () => {
  const { body } = await callOrca({ apiKey: "sk-orca-test", model: "openai/gpt-5.6-terra", fallbacks: ["openai/gpt-5.6-luna", "deepseek/deepseek-v4-flash"] });
  assert.deepEqual(body.models, ["openai/gpt-5.6-terra", "openai/gpt-5.6-luna", "deepseek/deepseek-v4-flash"]);
  assert.equal(body.route, "fallback");
});

test("OrcaRouter provider omits the fallback body when no fallbacks are configured", async () => {
  const { body } = await callOrca({ apiKey: "sk-orca-test", model: "openai/gpt-5.6-terra" });
  assert.equal(body.models, undefined);
  assert.equal(body.route, undefined);
});

test("OrcaRouter capability helpers classify provider-prefixed model ids", () => {
  assert.equal(bareModelId("openai/gpt-5.4"), "gpt-5.4");
  assert.equal(bareModelId("gpt-5.6-luna"), "gpt-5.6-luna");

  for (const model of ["openai/gpt-5", "openai/gpt-5.6-luna", "gpt-5.6-luna", "openai/o3-mini", "anthropic/claude-opus-4.7", "anthropic/claude-opus-4.5", "anthropic/claude-opus-5", "anthropic/claude-fable-5", "deepseek/deepseek-reasoner"]) {
    assert.equal(rejectsTemperature(model), true, `expected ${model} to reject temperature`);
  }
  for (const model of ["deepseek/deepseek-v4-flash", "openai/gpt-4o-mini", "anthropic/claude-sonnet-4.6", "anthropic/claude-opus-4", "google/gemini-3.6-flash", "orcarouter/auto"]) {
    assert.equal(rejectsTemperature(model), false, `expected ${model} to accept temperature`);
  }

  assert.equal(rejectsTopP("kimi/kimi-k3"), true);
  assert.equal(rejectsTopP("openai/gpt-5.4"), false);

  assert.equal(isOrcaRouterUrl("https://api.orcarouter.ai/v1"), true);
  assert.equal(isOrcaRouterUrl("https://api.openai.com/v1"), false);
  assert.equal(isOrcaRouterUrl(undefined), false);
});
