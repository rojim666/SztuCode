# Experimental LLM + Jev Agent Loop (TypeScript)

The TypeScript desktop daemon uses the configured LLM for reasoning and
TypeSafe Jev to choose among alternative next actions at meaningful choice
points. Direct tool calls and final answers do not require Jev approval.
The feature is disabled by default. Python behavior is unchanged.

## Enable

In the desktop workbench, open Settings > General > Experimental. Enter a
TypeSafe API key, optionally choose a Jev model and confidence threshold, then
enable **LLM + Jev Agent mode**. Saving configuration alone does not enable it.
The daemon also accepts `TYPESAFE_API_KEY`. The key is independent of the main
LLM key, is persisted using the existing runtime settings store, and is never
returned by `settings.get` or `settings.update`.

Settings apply to the next main Agent run. Turning the switch off restores the
standard loop for subsequent runs; cancel an active run before restarting it
in another mode. Model profile changes do not change the Jev settings.

The `settings.update` RPC accepts:

```json
{
  "experimental_jev": true,
  "jev_api_key": "YOUR_TYPESAFE_KEY",
  "jev_model": "jev-latest",
  "jev_confidence_threshold": 0.8
}
```

An empty `jev_api_key` clears the stored key; the environment key remains a
fallback. Enabling requires a configured key. Public settings include only
`jev_api_key_configured`, not the key itself. Protect the local settings file
as with the existing primary provider credentials.

## Decision Flow

1. The LLM uses the full conversation to reason. It calls ordinary tools directly
   for clear next steps and delivers final answers directly, with normal streaming.
2. At a meaningful choice point it calls `jev_select_action` **alone**. The input
   contains a `model_report` (`subgoal`, `assumptions`, `open_questions`) and 2–3
   independent alternative candidates. Each candidate has a unique `id`, `purpose`,
   `preconditions`, `expected_outcome`, and one complete `tool: {name, input}`.
   Sequential dependent steps must not be presented as alternatives.
3. The runtime validates the candidate structure, tool availability and every
   candidate's arguments. Unknown, recursive, identical, incomplete and mixed
   selector/ordinary batches execute nothing. No candidate arguments are truncated.
4. The official `@typesafe-ai/sdk` sends explicit task state and candidates to
   `POST /v1/systemone`. A typed `Choice` contains the candidate IDs plus
   `insufficient_information`. Jev selects; it does not generate tool arguments.
5. Above the configured confidence threshold, exactly one candidate is dispatched
   through the existing extension hooks, schema validation, permissions and
   scheduler. Existing tool retry policies still apply. Other candidates never
   execute. The original selector tool-call ID receives the selected action's
   actual result, preserving signed reasoning and valid provider tool history.
6. Low confidence, insufficient information, invalid candidates or an API error
   immediately return control to the full-context LLM. No uncertain candidate is
   executed automatically. The selection tool is removed for the rest of that run;
   the LLM generates a fresh direct action, gathers evidence, asks for information,
   or answers honestly. There is no three-rejection loop. The saved experiment
   switch remains unchanged; selection is available again on the next run.

Selection never grants permissions or certifies task completion. Final answers
and step-limit summaries use the ordinary path without a Jev call. Cancellation,
steering, step budgets and wall-clock limits remain effective. Steering during
selection discards the obsolete candidates and clears the old model report.
SDK errors are sanitized, with a visible fallback notice instead of credential
or response-body details. The SDK uses a 10-second per-attempt timeout and at
most one retry.

## Explicit Task State

A run-local state records:

- The run ID, goal and recent user steering.
- A runtime phase: reasoning, selecting, executing, needs_reasoning, responded,
  or stopped. `responded` means an answer was delivered, not that success was proven.
- The latest **unverified** model report: subgoal, assumptions and open questions.
- The last six actual tool outcomes, including call ID, step, tool, argument summary,
  success/error status and bounded textual output. Permission denials and failures
  remain visible. Model claims cannot write these observations.
- The selected candidate ID. `completion_verified` stays false: this component
  cannot certify overall completion. Check actual tests and acceptance evidence.

State survives context compaction within a run. Updated snapshots are appended
for the main model and restored after compaction, and Jev receives the in-memory
snapshot at each selection. The authoritative history remains tool results;
state is a bounded summary, not a replacement for the complete conversation.
It starts afresh for each run, with prior conversation retained by the main model.

`log.line` events with source `jev-state` expose state transitions and observed
outcomes; source `jev` records choices, confidence, threshold, resolved model and
input token usage separately from the main model's counters.

## Scope and Limits

This experiment applies to the desktop daemon's main `RunManager` loop. Subagents,
workflow workers, direct `AgentSession` consumers and compaction keep their
existing paths. Direct `AgentLoop` callers can inject a `jevDecision` controller.
The original tool registry is not modified by the experimental selector.

Task state, candidates and tool descriptions are shared with TypeSafe. Images,
file payloads and signed reasoning are excluded from extracted observations;
text and executable arguments can still contain task data. Text summaries are
bounded, and serialized state is capped at 28,000 UTF-8 bytes. Oversized payloads
return control to the LLM without a request or truncated executable arguments.
Jev sees partial evidence; the confidence threshold is a routing policy, not a
correctness guarantee. The LLM is responsible for proposing genuinely independent
alternatives and checking preconditions against actual evidence.

Upstream documentation checked on 2026-09-20 maps `jev-latest` and `jev-preview`
to `jev-1.13.0`. Use a versioned ID for reproducible evaluations. Jev is text-only,
with a 32k state-plus-longest-question limit.

## References

- [Introduction](https://docs.typesafe.ai/introduction)
- [JavaScript SDK](https://docs.typesafe.ai/sdk/javascript)
- [Models](https://docs.typesafe.ai/models)
- [Confidence](https://docs.typesafe.ai/confidence)
- [Building with System One](https://docs.typesafe.ai/concepts/how-to-build-with-system-one)

## Verification

```bash
npx tsx --test packages/runtime-ts/tests/jev.test.ts
cd desktop
npx playwright test tests/visual/jev-settings.spec.ts
```

Transport tests exercise the actual SDK with a mock HTTP response. These do not
measure live Jev decision quality, latency or calibration; those require a real
TypeSafe credential and representative task evaluations before broader rollout.
