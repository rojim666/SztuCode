/** Offline synthetic comparison of Jev state-injection overhead, not an API cost/quality eval. */
import { TokenCounter } from "../packages/runtime-ts/src/context.js";
import { JevContextProjection, JevTaskState } from "../packages/runtime-ts/src/jev.js";
import type { ChatMessage } from "../packages/runtime-ts/src/agent-loop.js";

const counter = new TokenCounter();
const scenarios = [
  { name: "short-results", output: "Found a matching declaration. ".repeat(4), compactAt: 0 },
  { name: "long-results", output: "export function parseConfig(input: string) { return JSON.parse(input); }\n".repeat(20), compactAt: 0 },
  { name: "chinese-results-with-compaction", output: "校验失败：配置项缺失，需要检查调用方提供的参数。\n".repeat(30), compactAt: 10 },
];
const results = scenarios.map(scenario => {
  const state = new JevTaskState("Locate the configuration contract and identify the smallest fix", "offline-benchmark");
  state.value.model_report = { subgoal: "Inspect configuration evidence", assumptions: ["The contract may be defined at the caller"], open_questions: ["Which caller supplies the missing field?"] };
  const projection = new JevContextProjection();
  let oldMessages: ChatMessage[] = [], newMessages: ChatMessage[] = [];
  let oldAdded = 0, newAdded = 0, oldPromptAppearances = 0, newPromptAppearances = 0;
  const stateTokens = (messages: ChatMessage[]) => messages.reduce((total, message) =>
    total + (typeof message.content === "string" && message.content.startsWith("Experimental task state") ? counter.count(message.content) : 0), 0);
  for (let step = 1; step <= 20; step++) {
    if (step === scenario.compactAt) {
      // Retain recent tool pairs, dropping earlier state bases as compaction can do.
      oldMessages = oldMessages.slice(-2);
      newMessages = newMessages.slice(-2);
    }
    const oldMessage: ChatMessage = { role: "user", content: `Experimental task state (model_report is unverified; observations are actual tool results, not overall completion):\n${JSON.stringify(state.snapshot())}` };
    oldMessages.push(oldMessage);
    oldAdded += counter.count(String(oldMessage.content));
    const projected = projection.next(state.snapshot(), newMessages);
    if (projected) { newMessages.push(projected); newAdded += counter.count(String(projected.content)); }
    oldPromptAppearances += stateTokens(oldMessages);
    newPromptAppearances += stateTokens(newMessages);
    const call = { id: `inspect-${step}`, name: "read_file", input: { path: `src/config-${step}.ts` } };
    const result = { ok: step % 4 !== 0, output: scenario.output };
    const pair: ChatMessage[] = [
      { role: "assistant", content: "", tool_calls: [call] },
      { role: "tool", tool_call_id: call.id, content: result.output, is_error: !result.ok },
    ];
    oldMessages.push(...pair); newMessages.push(...pair);
    state.observe(step, call, result);
  }
  return {
    scenario: scenario.name, llm_turns: 20,
    state_tokens_appended_before: oldAdded, state_tokens_appended_after: newAdded,
    reduction_pct: Number(((1 - newAdded / oldAdded) * 100).toFixed(1)),
    state_token_appearances_across_prompts_before: oldPromptAppearances,
    state_token_appearances_across_prompts_after: newPromptAppearances,
  };
});
console.log(JSON.stringify({
  kind: "synthetic_offline_context_benchmark", tokenizer: counter.preciseAvailable ? "o200k_base" : "heuristic_fallback",
  caveats: ["Measures only Jev state-injection overhead, not all task tokens or billed savings.", "Prompt appearances include cached re-reads; do not price them as uncached input.", "No model calls; no evidence of improved coding accuracy or latency."],
  results,
}, null, 2));
