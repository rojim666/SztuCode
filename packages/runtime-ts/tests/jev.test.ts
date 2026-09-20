import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { Socket } from "node:net";
import { JevController, JEV_PLANNER_INSTRUCTION, JEV_FALLBACK_INSTRUCTION, JEV_SELECT_TOOL, JevTaskState, JevContextProjection, type JevPlan, type JevDecisionProvider } from "../src/jev.js";
import { AgentLoop, type ChatMessage, type ModelProvider, type ModelResponse } from "../src/agent-loop.js";
import { ToolRegistry } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";
import { EventBus } from "../src/event-bus.js";
import { SettingsStore } from "../src/settings.js";
import { normalizeSettingsUpdate, validateSetting } from "../src/server-helpers.js";
import { ModelProfileStore } from "../src/model-profiles.js";
import { RuntimeServer } from "../src/server.js";

const proposal: ModelResponse = { text: "Inspect the file", stop_reason: "tool_use", tool_calls: [{ id: "call-1", name: "inspect", input: { path: "README.md" } }], usage: { input_tokens: 10, output_tokens: 2 } };
const final: ModelResponse = { text: "Verified answer", tool_calls: [], stop_reason: "end_turn", usage: { input_tokens: 20, output_tokens: 3 } };
const plan = (): JevPlan => ({ model_report: { subgoal: "Find the documented contract", assumptions: ["Documentation may contain the contract"], open_questions: ["Which source is authoritative?"] }, candidates: [
  { id: "readme", purpose: "Read overview", preconditions: ["README is available"], expected_outcome: "Learn the contract", tool: { name: "inspect", input: { path: "README.md" } } },
  { id: "source", purpose: "Read implementation", preconditions: ["Source is available"], expected_outcome: "Learn actual behavior", tool: { name: "inspect", input: { path: "main.ts" } } },
] });
const selection = (input = plan()): ModelResponse => ({ ...proposal, tool_calls: [{ id: "select-1", name: JEV_SELECT_TOOL, input: input as unknown as Record<string, unknown> }] });
const reply = (selected: string, confidence = 0.95) => Response.json({ model: "jev-1.13.0", answers: { next: { type: "choice", choice: selected, confidence, probabilities: { [selected]: confidence } } }, usage: { input_tokens: 17, output_tokens: 0 } });


async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-jev-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  const tokens: string[] = [], paths: string[] = [], states: any[] = [], logs: string[] = [];
  events.subscribe(event => {
    if (event.type === "llm.token") tokens.push(event.token);
    if (event.type === "log.line") { logs.push(event.message); if (event.source === "jev-state") states.push(JSON.parse(event.message)); }
  });
  const tools = new ToolRegistry();
  tools.register({ name: "inspect", description: "Inspect a file", schema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] }, permission: "read_only", invoke: async input => { paths.push(String(input.path)); return { ok: true, output: "File evidence" }; } });
  return { root, events, tokens, tools, paths, states, logs, cleanup: async () => { await events.flush(); await rm(root, { recursive: true, force: true }); } };
}

function assertPaired(messages: ChatMessage[]) {
  for (let index = 0; index < messages.length; index++) {
    const message = messages[index];
    if (message.role !== "assistant" || !message.tool_calls?.length) continue;
    const results = messages.slice(index + 1, index + 1 + message.tool_calls.length);
    assert.deepEqual(results.map(m => [m.role, m.tool_call_id]), message.tool_calls.map(call => ["tool", call.id]));
  }
}

test("SDK selects among candidates with explicit state, independent credentials, bounded visible evidence", async () => {
  const f = await fixture();
  try {
    let request: any;
    const controller = new JevController({ apiKey: "jev-test-key", fetch: async (url, init) => {
      assert.equal(url, "https://api.typesafe.ai/v1/systemone");
      assert.equal(new Headers(init?.headers).get("authorization"), "Bearer jev-test-key");
      request = JSON.parse(String(init?.body)); return reply("source");
    } });
    const state = new JevTaskState("Find contract");
    state.steer([{ role: "user", content: [{ type: "text", text: "Inspect sources" }, { type: "image", source: { media_type: "image/png", data: "SECRET_IMAGE_BYTES" } }, { type: "thinking", thinking: "PRIVATE_REASONING", signature: "SIGNED" }] }]);
    state.value.model_report = plan().model_report;
    state.observe(1, proposal.tool_calls[0], { ok: false, output: "Missing file", errorType: "runtime_error" });
    const result = await controller.decide(state.snapshot(), plan().candidates, f.tools);
    assert.equal(result.action, "select"); assert.equal(result.candidateId, "source"); assert.equal(result.inputTokens, 17);
    assert.equal(result.apiCalled, true);
    assert.deepEqual(result.probabilities, { source: 0.95 });
    assert.equal(result.stateBytes, Buffer.byteLength(JSON.stringify(request.state), "utf8"));
    assert.equal(request.model, "jev-latest"); assert.equal(request.questions.next.type, "choice");
    assert.deepEqual(request.state.candidates, plan().candidates);
    assert.equal(request.state.task.observations[0].ok, false);
    assert.equal(request.state.task.completion_verified, false);
    assert.doesNotMatch(JSON.stringify(request), /SECRET_IMAGE_BYTES|PRIVATE_REASONING|SIGNED/);
    const low = new JevController({ apiKey: "test", fetch: async () => reply("source", 0.4) });
    const uncertain = await low.decide(state.snapshot(), plan().candidates, f.tools);
    assert.equal(uncertain.action, "defer"); assert.match(uncertain.reason, /0\.40.*0\.80/);
    const insufficient = new JevController({ apiKey: "test", fetch: async () => reply("insufficient_information") });
    assert.equal((await insufficient.decide(state.snapshot(), plan().candidates, f.tools)).action, "defer");
    const invalid = new JevController({ apiKey: "test", fetch: async () => reply("invented") });
    await assert.rejects(invalid.decide(state.snapshot(), plan().candidates, f.tools), /Invalid/);
    const huge = plan(); huge.candidates[0].tool.input.path = "x".repeat(30_000);
    const noFetch = new JevController({ apiKey: "test", fetch: async () => { throw new Error("Must not fetch"); } });
    const oversized = await noFetch.decide(state.snapshot(), huge.candidates, f.tools);
    assert.match(oversized.reason, /too large/);
    assert.equal(oversized.apiCalled, false);
    assert.ok(oversized.stateBytes! > 28_000);
  } finally { await f.cleanup(); }
});

test("only the selected candidate executes once; observations, signed history and permission checks remain accurate", async () => {
  for (const allowed of [true, false]) {
    const f = await fixture();
    try {
      let calls = 0, decisions = 0, checks = 0;
      const jev: JevDecisionProvider = { decide: async (state, candidates) => {
        decisions++; assert.equal(state.phase, "selecting"); assert.deepEqual(state.observations, []);
        assert.equal(state.model_report?.subgoal, plan().model_report.subgoal);
        assert.equal(candidates.length, 2); return { action: "select", candidateId: "source", confidence: 0.95, reason: "Prefer source" };
      } };
      const provider: ModelProvider = { complete: async (messages, tools, _signal, onToken) => {
        assert.ok(tools.get(JEV_SELECT_TOOL));
        if (calls > 0) {
          assertPaired(messages);
          assert.match(JSON.stringify(messages), /SIGNED_REASONING/);
          assert.match(JSON.stringify(messages), allowed ? /File evidence/ : /Permission denied/);
        }
        const response = calls++ === 0 ? { ...selection(), thinking_blocks: [{ type: "thinking", thinking: "Choose an approach", signature: "SIGNED_REASONING" }] } : final;
        onToken?.(response.text); return { ...response, streamed: true };
      } };
      const result = await new AgentLoop(provider, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async (_r, _id, _tool, input) => { checks++; assert.equal(input.path, "main.ts"); return allowed; } }, { jevDecision: jev, streaming: true, compactThreshold: 0 }).run("r", "inspect", 4);
      assert.equal(decisions, 1); assert.equal(checks, 1);
      assert.deepEqual(f.paths, allowed ? ["main.ts"] : []);
      assert.deepEqual(f.tokens, [proposal.text, final.text]);
      assert.equal(result.usage.input_tokens, 30);
      assertPaired(result.messages);
      const state = f.states.at(-1);
      assert.equal(state.phase, "responded"); assert.equal(state.completion_verified, false);
      assert.equal(state.observations.length, 1); assert.equal(state.observations[0].ok, allowed);
      assert.equal(state.observations[0].tool, "inspect");
      assert.equal(f.tools.get(JEV_SELECT_TOOL), undefined, "Do not mutate shared tool registry");
      const decisionLog = f.logs.map(line => { try { return JSON.parse(line); } catch { return {}; } }).find(log => log.action === "select");
      assert.equal(decisionLog.candidate_count, 2);
      assert.ok(decisionLog.elapsed_ms >= 0);
    } finally { await f.cleanup(); }
  }
});

test("direct tools and final answers stream without any Jev approval", async () => {
  const f = await fixture();
  try {
    let calls = 0;
    const provider: ModelProvider = { complete: async (_m, _t, _s, onToken) => { const response = calls++ ? final : proposal; onToken?.(response.text); return { ...response, streamed: true }; } };
    const result = await new AgentLoop(provider, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async () => true }, { jevDecision: { decide: async () => { throw new Error("Must never evaluate direct actions or answers"); } }, streaming: true, compactThreshold: 0 }).run("r", "inspect", 3);
    assert.equal(result.text, final.text); assert.deepEqual(f.paths, ["README.md"]); assert.deepEqual(f.tokens, [proposal.text, final.text]);
  } finally { await f.cleanup(); }
});

test("one uncertain selection or API error returns control to the LLM without executing any candidate or leaking errors", async () => {
  for (const fail of [false, true]) {
    const f = await fixture();
    try {
      let calls = 0, decisions = 0;
      const jev = new JevController({ apiKey: "test", retry: { maxRetries: 0 }, fetch: async () => { decisions++; if (fail) throw new Error("SECRET_API_KEY response body"); return reply("source", 0.39); } });
      const provider: ModelProvider = { complete: async (messages, tools) => {
        if (calls === 1) {
          assert.equal(f.paths.length, 0); assert.equal(tools.get(JEV_SELECT_TOOL), undefined);
          assertPaired(messages); assert.ok(messages.some(m => m.content === JEV_FALLBACK_INSTRUCTION));
        }
        return [selection(), { ...proposal, tool_calls: [{ ...proposal.tool_calls[0], id: "fresh" }] }, final][calls++];
      } };
      const result = await new AgentLoop(provider, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async () => true }, { jevDecision: jev, compactThreshold: 0 }).run("r", "inspect", 4);
      assert.equal(result.steps, 3); assert.equal(decisions, 1); assert.deepEqual(f.paths, ["README.md"]);
      assert.doesNotMatch(JSON.stringify([result.messages, f.logs]), /SECRET_API_KEY|response body/); assertPaired(result.messages);
    } finally { await f.cleanup(); }
  }
});

test("invalid, mixed, incomplete, recursive and duplicate candidate sets execute nothing and make no Jev call", async () => {
  const badInputs: ModelResponse[] = [];
  const unknown = plan(); unknown.candidates[0].tool.name = "unknown"; badInputs.push(selection(unknown));
  const recursive = plan(); recursive.candidates[0].tool.name = JEV_SELECT_TOOL; badInputs.push(selection(recursive));
  const args = plan(); args.candidates[0].tool.input = { path: 2 }; badInputs.push(selection(args));
  const duplicate = plan(); duplicate.candidates[1].id = "readme"; badInputs.push(selection(duplicate));
  const same = plan(); same.candidates[1].tool = same.candidates[0].tool; badInputs.push(selection(same));
  const single = plan(); single.candidates.pop(); badInputs.push(selection(single));
  badInputs.push({ ...selection(), tool_calls: [...selection().tool_calls, ...proposal.tool_calls] });
  badInputs.push({ ...selection(), stop_reason: "max_tokens" });
  for (const bad of badInputs) {
    const f = await fixture();
    try {
      let calls = 0, decisions = 0;
      const result = await new AgentLoop({ complete: async () => calls++ ? final : bad }, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async () => { throw new Error("No tools allowed"); } }, { jevDecision: { decide: async () => { decisions++; throw new Error("No API calls"); } }, compactThreshold: 0 }).run("r", "inspect", 3);
      assert.equal(decisions, 0); assert.equal(f.paths.length, 0); assertPaired(result.messages);
    } finally { await f.cleanup(); }
  }
});

test("cancellation and steering during selection cannot execute obsolete candidates", async () => {
  for (const steer of [false, true]) {
    const f = await fixture();
    try {
      const abort = new AbortController(); let generation = new AbortController();
      const pending: ChatMessage[] = []; let decisions = 0;
      const jev: JevDecisionProvider = { decide: async (_state, _candidates, _tools, signal) => {
        decisions++;
        if (steer) { pending.push({ role: "user", content: "Do not inspect anything" }); generation.abort(); }
        else abort.abort(new Error("User cancelled"));
        signal?.throwIfAborted(); return { action: "select", candidateId: "source", confidence: 1, reason: "source" };
      } };
      const provider: ModelProvider = { complete: async messages => {
        if (decisions) { assert.ok(messages.some(message => message.content === "Do not inspect anything")); assertPaired(messages); }
        return decisions ? final : selection();
      } };
      const loop = new AgentLoop(provider, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async () => true }, { jevDecision: jev, compactThreshold: 0 });
      const result = loop.run("r", "inspect", 4, [], abort.signal, () => { const values = pending.splice(0); if (generation.signal.aborted) generation = new AbortController(); return values; }, () => generation.signal);
      if (steer) { assert.equal((await result).text, final.text); assert.deepEqual(f.states.at(-1).latest_user_requests, ["Do not inspect anything"]); }
      else await assert.rejects(result, /User cancelled/);
      assert.equal(f.paths.length, 0);
    } finally { await f.cleanup(); }
  }
});

test("step budgets still conclude without Jev approval; inconclusive choices do not skip budgets", async () => {
  for (const selected of [true, false]) {
    const f = await fixture();
    try {
      let calls = 0, decisions = 0;
      const provider: ModelProvider = { complete: async (_m, tools) => {
        if (calls++ === 0) return selection();
        assert.equal(tools.list().length, 0); return { ...final, text: "[INCOMPLETE] Need further evidence" };
      } };
      const loop = new AgentLoop(provider, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async () => true }, { compactThreshold: 0, jevDecision: { decide: async () => { decisions++; return selected ? { action: "select", candidateId: "source", confidence: 1, reason: "source" } : { action: "defer", confidence: 0.3, reason: "uncertain" }; } } });
      await assert.rejects(loop.run("r", "work", 1), /exceeded max steps/);
      assert.equal(calls, 2); assert.equal(decisions, 1); assert.deepEqual(f.paths, selected ? ["main.ts"] : []);
    } finally { await f.cleanup(); }
  }
});

test("wall clock budget expires before selected tool dispatch", async () => {
  const f = await fixture();
  try {
    const loop = new AgentLoop({ complete: async () => selection() }, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async () => true }, { compactThreshold: 0, maxWallClockMs: 50, jevDecision: { decide: async () => { await new Promise(resolve => setTimeout(resolve, 70)); return { action: "select", candidateId: "source", confidence: 1, reason: "source" }; } } });
    await assert.rejects(loop.run("r", "work", 3), /time budget/); assert.equal(f.paths.length, 0);
  } finally { await f.cleanup(); }
});

test("state is bounded and preserves failed outcomes separately from model claims", async () => {
  const state = new JevTaskState("goal");
  state.value.model_report = { subgoal: "Done", assumptions: ["All tests passed"], open_questions: [] };
  for (let i = 0; i < 12; i++) state.observe(i, proposal.tool_calls[0], { ok: false, output: "x".repeat(5000), errorType: "permission_denied" });
  assert.equal(state.snapshot().observations.length, 6); assert.equal(state.snapshot().completion_verified, false);
  assert.equal(state.snapshot().phase, "needs_reasoning");
  assert.ok(state.snapshot().observations[0].output.length < 1200);
  const snapshot = state.snapshot(); snapshot.observations.length = 0;
  assert.equal(state.snapshot().observations.length, 6);
});

test("candidate state survives compaction and later choices see actual failed outcomes", async () => {
  const f = await fixture();
  try {
    let calls = 0, decisions = 0, compactions = 0;
    const provider: ModelProvider = { complete: async (_messages, _tools, _signal, _token, invocation) => {
      if (invocation?.purpose === "compaction") {
        compactions++;
        return { ...final, text: "Goal\nFind contract.\nProgress\nOld turns summarized.\nDecisions\nUse evidence.\nOpen Issues\nMissing source.\nNext Steps\nInspect." };
      }
      return calls++ < 2 ? { ...selection(), usage: { input_tokens: 80_000 } } : final;
    } };
    const jev: JevDecisionProvider = { decide: async state => {
      if (decisions++) {
        assert.ok(compactions > 0);
        assert.equal(state.observations.length, 1);
        assert.equal(state.observations[0].ok, false);
        assert.equal(state.observations[0].error_type, "permission_denied");
        assert.equal(state.observations[0].tool, "inspect");
        assert.match(state.observations[0].input_summary, /main.ts/);
      }
      return { action: "select", candidateId: "source", confidence: 1, reason: "source" };
    } };
    const history: ChatMessage[] = [{ role: "user", content: "Find contract" }, ...Array.from({ length: 8 }, (_, i) => ({ role: (i % 2 ? "user" : "assistant") as "user" | "assistant", content: `turn-${i} ${"detail ".repeat(20)}` }))];
    const result = await new AgentLoop(provider, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async () => false }, { jevDecision: jev, contextWindow: 100_000, compactThreshold: 0.7, slidingWindowSize: 2, compactMinimumOldTokens: 0 }).run("r", "inspect", 4, history);
    assert.equal(result.compacted, true); assert.equal(decisions, 2); assert.equal(f.paths.length, 0); assertPaired(result.messages);
  } finally { await f.cleanup(); }
});

test("LLM task-state deltas avoid repeating tool evidence and unchanged reports", () => {
  const state = new JevTaskState("Find the contract", "projection");
  state.value.model_report = plan().model_report;
  const projection = new JevContextProjection();
  const messages: ChatMessage[] = [];
  const first = projection.next(state.snapshot(), messages)!;
  messages.push(first);
  assert.match(String(first.content), /snapshot/);
  assert.equal(projection.next(state.snapshot(), messages), undefined);
  const evidence: ChatMessage = { role: "tool", tool_call_id: "call-1", content: "UNIQUE_TOOL_EVIDENCE" };
  messages.push({ role: "assistant", content: "", tool_calls: proposal.tool_calls }, evidence);
  state.observe(1, proposal.tool_calls[0], { ok: true, output: "UNIQUE_TOOL_EVIDENCE" });
  const delta = projection.next(state.snapshot(), messages)!;
  messages.push(delta);
  assert.match(String(delta.content), /"update_type":"delta"/);
  assert.match(String(delta.content), /"call_id":"call-1"/);
  assert.doesNotMatch(String(delta.content), /UNIQUE_TOOL_EVIDENCE|Find the contract|"model_report"/);
  assert.equal(messages.filter(message => String(message.content).includes("UNIQUE_TOOL_EVIDENCE")).length, 1);
  assert.equal(state.snapshot().observations[0].output, "UNIQUE_TOOL_EVIDENCE", "Jev still gets the complete bounded state");
  assert.equal(projection.next(state.snapshot(), messages), undefined);
  state.steer([{ role: "user", content: "Stop inspecting, explain the issue" }]);
  const steering = projection.next(state.snapshot(), messages)!;
  assert.match(String(steering.content), /"model_report":null/);
  assert.match(String(steering.content), /Stop inspecting/);
});

test("compaction restores the base and lost evidence even when a later delta survives", () => {
  const state = new JevTaskState("Keep the real goal", "projection");
  state.value.model_report = plan().model_report;
  const projection = new JevContextProjection();
  const messages: ChatMessage[] = [];
  messages.push(projection.next(state.snapshot(), messages)!);
  const evidence: ChatMessage = { role: "tool", tool_call_id: "call-1", content: "Permission denied", is_error: true };
  messages.push(evidence);
  state.observe(1, proposal.tool_calls[0], { ok: false, output: "Permission denied", errorType: "permission_denied" });
  const delta = projection.next(state.snapshot(), messages)!;
  const compacted = [delta];
  const restored = projection.next(state.snapshot(), compacted)!;
  assert.match(String(restored.content), /"update_type":"snapshot"/);
  assert.match(String(restored.content), /Keep the real goal|Find the documented contract/);
  assert.match(String(restored.content), /"ok":false/);
  assert.match(String(restored.content), /Permission denied/);
  compacted.push(restored);
  assert.equal(projection.next(state.snapshot(), compacted), undefined);
});

test("losing referenced evidence alone restores its bounded text without inventing success", () => {
  const state = new JevTaskState("Inspect", "projection");
  const projection = new JevContextProjection();
  const messages: ChatMessage[] = [];
  messages.push(projection.next(state.snapshot(), messages)!);
  const evidence: ChatMessage = { role: "tool", tool_call_id: "call-1", content: "Failed check", is_error: true };
  messages.push(evidence);
  state.observe(1, proposal.tool_calls[0], { ok: false, output: "Failed check" });
  messages.push(projection.next(state.snapshot(), messages)!);
  messages.splice(messages.indexOf(evidence), 1);
  const restored = projection.next(state.snapshot(), messages)!;
  assert.match(String(restored.content), /Failed check/);
  assert.match(String(restored.content), /"completion_verified":false/);
  messages.push(restored);
  assert.equal(projection.next(state.snapshot(), messages), undefined);
});

test("standard loop has no experimental tools, state, or instruction", async () => {
  const f = await fixture();
  try {
    const provider: ModelProvider = { complete: async (_m, tools, _s, onToken) => { assert.equal(tools.get(JEV_SELECT_TOOL), undefined); onToken?.(final.text); return { ...final, streamed: true }; } };
    const result = await new AgentLoop(provider, f.tools, { workspace: new Workspace(f.root) }, f.events, { check: async () => true }, { streaming: true }).run("r", "work", 1);
    assert.equal(result.text, final.text); assert.deepEqual(f.tokens, [final.text]); assert.equal(f.states.length, 0);
    assert.ok(!JSON.stringify(result.messages).includes(JEV_PLANNER_INSTRUCTION));
  } finally { await f.cleanup(); }
});

test("Jev settings default off, persist, redact credentials and remain separate from model profiles", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-jev-settings-"));
  try {
    const file = path.join(root, "settings.json");
    await writeFile(file, JSON.stringify({ model: "legacy-model" }));
    const settings = new SettingsStore(file);
    assert.equal((await settings.get()).experimental_jev, false);
    const input = { experimental_jev: true, jev_api_key: "test-secret", jev_model: "jev-1.13.0", jev_confidence_threshold: 0.9 };
    const normalized = normalizeSettingsUpdate(input, await settings.getProviderConfig());
    assert.deepEqual(new Set(normalized.updated), new Set(Object.keys(input)));
    const publicSettings = await settings.update(normalized.update);
    assert.equal(publicSettings.jev_api_key_configured, true);
    assert.doesNotMatch(JSON.stringify(publicSettings), /test-secret/);
    assert.equal((await new SettingsStore(file).get()).experimental_jev, true);
    const profiles = new ModelProfileStore(settings, path.join(root, "profiles.json"));
    await profiles.select("builtin-opencode-zen-big-pickle");
    assert.equal((await settings.get()).experimental_jev, true);
    assert.equal((await settings.get()).jev_model, "jev-1.13.0");
    assert.doesNotMatch(await readFile(path.join(root, "profiles.json"), "utf8"), /jev_|experimental_jev|test-secret/);
    await settings.update({ experimental_jev: false, jev_api_key: "" });
    for (const [key, value] of [["experimental_jev", "true"], ["jev_confidence_threshold", NaN], ["jev_confidence_threshold", 1.1], ["jev_model", " "]] as const) assert.throws(() => validateSetting(key, value));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("desktop daemon RPC settings enable Jev on the next run and disabling makes no further TypeSafe requests", { timeout: 15_000 }, async t => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-jev-daemon-"));
  const previousData = process.env.SZTU_DATA_DIR;
  process.env.SZTU_DATA_DIR = root;
  let modelCalls = 0;
  const server = new RuntimeServer("127.0.0.1", 0, { complete: async (_messages, tools) => {
    if (modelCalls++ === 0 && tools.get(JEV_SELECT_TOOL)) {
      const planned = plan();
      for (const candidate of planned.candidates) candidate.tool = { name: "list_dir", input: { path: candidate.id === "readme" ? "." : "src" } };
      return selection(planned);
    }
    return final;
  } });
  const socket = new Socket();
  let evaluations = 0;
  t.mock.method(globalThis, "fetch", async (_url: string, init?: RequestInit) => {
    evaluations++;
    const body = JSON.parse(String(init?.body));
    assert.equal(body.model, "jev-1.13.0");
    assert.equal(body.questions.next.type, "choice");
    return reply("readme");
  });
  const run = async () => {
    modelCalls = 0;
    const finished = new Promise<string>(resolve => {
      const unsubscribe = server.events.subscribe(event => {
        if (event.type === "run.finished") { unsubscribe(); resolve(event.status); }
      });
    });
    server.runs.start("Answer using the supplied evidence", [], undefined, root);
    assert.equal(await finished, "success");
  };
  try {
    await run(); assert.equal(evaluations, 0);
    const response = await server.service.dispatch.call(server, { jsonrpc: "2.0", id: "enable", method: "settings.update", params: { experimental_jev: true, jev_api_key: "independent-secret", jev_model: "jev-1.13.0", jev_confidence_threshold: 0.8 } }, socket);
    assert.ok("result" in response);
    assert.doesNotMatch(JSON.stringify(response), /independent-secret/);
    await run(); assert.equal(evaluations, 1);
    await server.service.dispatch.call(server, { jsonrpc: "2.0", id: "disable", method: "settings.update", params: { experimental_jev: false } }, socket);
    await run(); assert.equal(evaluations, 1);
  } finally {
    await server.close(); socket.destroy();
    if (previousData === undefined) delete process.env.SZTU_DATA_DIR; else process.env.SZTU_DATA_DIR = previousData;
    await rm(root, { recursive: true, force: true });
  }
});
