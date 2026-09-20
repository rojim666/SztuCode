# Jev in the TypeScript Coding Agent: cost and decision efficiency

Research and implementation checkpoint: 2026-09-21, Asia/Shanghai.

## Main finding

The current LLM → candidates → Jev → tool loop adds a decision service after
the LLM has already reasoned. It cannot inherently save a primary-model turn.
Generating unused candidate arguments and repeating state can make it more
expensive. Its value must come from avoiding bad actions, reducing later context,
or eventually replacing a bounded reasoning turn. These are separate hypotheses.

TypeSafe's documented design is consistent with this: code owns the workflow;
Jev answers small, explicit semantic questions. Complex programming, novel fixes,
multi-hop reasoning and code generation stay with the reasoning LLM. Deterministic
schema, permission, dependency, numeric and test-result checks stay in code.

## Changes implemented now

`JevContextProjection` in `packages/runtime-ts/src/jev.ts` produces an append-only
view for the primary model. Unchanged goals, model reports and old observations
are not repeated each turn. When a tool result is already in context, the state
update references its call ID and status instead of copying its output and input.

The runtime tracks both the delta chain and evidence sources. Losing an earlier
base or a referenced tool message causes a bounded full snapshot to be restored,
including missing output summaries. Budget-triggered compaction restores state
before the next provider request. It does not rewrite cached prompt prefixes.
Jev still receives the original bounded state; this optimization changes the
primary model's redundant context, not Jev's inputs or routing thresholds.

Decision logs now include probability distributions, candidate counts, state
bytes, elapsed milliseconds and whether the API was called. State bytes are not
token counts; input usage comes from the SDK. Error-path API usage can be unknown.
Aborted selections are not a complete billed-usage ledger. Provider billing must
be used to reconcile retries, failures and cancelled requests in a cost study.

## Offline token benchmark

Reproduce with `npx tsx scripts/bench-jev-context.ts`.

The benchmark runs 20 synthetic turns per scenario using the repository's
`o200k_base` tokenizer. It compares the previous full-state injection to the new
projection, retaining identical tool results. It measures **only state-injection
overhead**, not all task tokens, model quality, latency or dollars.

- Short tool results: 8,441 → 1,628 newly appended state tokens, down 80.7%.
- Long tool results: 30,735 → 1,628, down 94.7%.
- Chinese results with a compaction at turn 10: 32,220 → 3,219, down 90.0%.

The script also counts how often these tokens occur across subsequent prompts.
Those appearances include cached rereads. Multiplying all appearances by the
uncached input price would substantially overstate savings. Our local partial
trace has substantial cache-read usage, reinforcing the need for separate cache
accounting. The trace is not a randomized or paired experiment.

## Live synthetic pilot

Reproduce with:

```bash
npx tsx scripts/eval-jev-retrieval.ts
npx tsx scripts/eval-jev-retrieval.ts --live --output docs/architecture/jev-retrieval-pilot.json
```

The first command previews the experiment without an API request. The second
uses `TYPESAFE_API_KEY` or the saved Jev credential. It sends only the handwritten
snippets embedded in the script, executes no tools, and does not change settings.

The recorded pilot uses pinned `jev-1.13.0`, 12 manually labelled cases, and two
requests per case. Cases cover permission checks, cancellation, persistence,
Chinese queries, missing evidence, comment-only evidence, an injected comment,
and equivalent valid sources. All 24 requests completed.

Raw results are in [jev-retrieval-pilot.json](jev-retrieval-pilot.json).

- Existing candidate-selector format: 10/12 selected labels match the direct-
  implementation labels; 14,034 input tokens; p50 330 ms, p95 1,674 ms.
- Narrow retrieval question: 12/12 label matches; 5,876 input tokens; p50 311 ms,
  p95 1,314 ms. Its question asks which excerpt directly implements the behavior,
  with an explicit NONE outcome for no supporting implementation.
- At confidence 0.8, both formats automatically select 9/12 cases, all matching
  the acceptable labels. The narrow format correctly returns NONE for two cases
  and defers one equivalent-options case for low confidence.

Input usage is 58.1% lower for the narrow format in this pilot. At the documented
$0.042 per million input tokens, all 24 requests together cost an estimated
$0.00083622 in Jev input charges. This excludes primary-model candidate generation
and is an estimate from usage, not an invoice. Output tokens are documented as free.

**These are not equivalent classifiers.** Selecting a useful next action can
reasonably select a file to inspect even when the excerpt does not yet implement
the requested behavior. A direct-implementation retrieval label would mark that
choice wrong. The pilot demonstrates the importance of matching the question to
its evaluation target; it is not evidence that the production action selector has
a 16.7% error rate or that coding-task success improved. It is also too small to
establish a production error bound or statistically meaningful latency difference.

The equivalent-options example is particularly relevant: both A and B were valid,
but confidence was 0.51 for the generic selector and 0.68 for the narrow question.
With a 0.8 threshold, both defer a perfectly valid selection. Ambiguous rankings
are not the same as unsafe or incorrect actions. Do not lower the production
threshold based on this tiny sample; improve the decision contract first.

## Highest-value next integration: retrieval before the LLM

The existing `semantic_search` merges lexical/vector candidates in
`packages/runtime-ts/src/tools.ts`, then calls `deduplicateBySource` in
`packages/runtime-ts/src/retrieval/hybrid-search.ts`. This is a concrete seam for
a separate experimental reranker.

1. Keep exact path/symbol matches and deterministic project filters in code.
2. Retrieve a modest shortlist, initially 8–12 bounded snippets as an experiment.
3. Ask an independent relevance question per snippet in one Jev request. Each
   question points directly to its own snippet and the unresolved coding question.
4. Compose the results in code and retain a small, token-bounded set for the LLM.
   Retain source paths, line ranges and content hashes so evidence remains traceable.
5. On low confidence, no relevant result, timeout or an oversized request, return
   the existing search results. A reranker must not silently erase essential evidence.

Multiple snippets can be useful simultaneously. Per-snippet relevance (`Noul`, or
an ordered `Score` rubric) is a better fit than a forced single-winner `Choice`.
Noul has a yes-probability, not the same confidence field as Choice/Score. Do not
reuse the current confidence threshold mechanically. Scores should be anchored to
semantic levels, such as direct implementation, supporting caller, or unrelated.

The saving mechanism is fewer irrelevant snippets passed through later expensive
LLM turns. The additional Jev request is only justified if it improves retrieval
or downstream cost enough to cover its token and latency cost. First run in shadow
mode, recording what would have been retained while preserving existing output.

Skill selection is a similar opportunity, but its priority depends on measured
catalogue size and irrelevant skill loads. Do not add a model call when deterministic
skill naming or a small catalogue already suffices.

## Next way to save whole LLM turns: bounded plan continuation

The current candidate tool selects only one step. A later experiment could let the
LLM emit a typed, bounded plan with complete actions, observable branch conditions,
expected evidence and an explicit replan condition. Existing display-only plan
items must not be treated as executable instructions without a new typed contract.

Code validates the plan and tracks executable actions:

- No ready action or unexpected evidence: return to the LLM with the actual result.
- Exactly one ready action: execute through existing checks without Jev.
- Multiple independent ready reads/searches: Jev answers a narrow prioritization
  question over relevant observations; code chooses only within the validated set.
- Stop after a small continuation budget, for example two actions initially, or
  immediately on steering, stale file hashes, failed preconditions or uncertainty.

This is where a Jev decision can replace an LLM turn instead of being appended after
one. Do not reuse old candidate arguments after repository state changes. Do not
speculatively execute writes. Tool permission checks remain at execution time.
Completion still depends on tests/acceptance evidence and an honest final response.

## Make decision quality measurable

Give each decision one objective. For example: “which snippet contains the symbol's
implementation?” or “does this error indicate missing environment configuration?”
Avoid mixing relevance, risk, completeness, cost and expected progress into one
opaque score. Independent semantic questions can share one API call, but dependent
questions need explicit sequencing. More questions still consume input budget.

For coding failures, use exit codes, error types and structured test reports first.
Jev may help classify ambiguous prose into configuration, regression, flaky test,
or insufficient evidence. It should not reinterpret a failing exit code as success
or certify the correctness of a patch.

Construct a small decision packet from relevant evidence instead of always taking
the last six results. Keep file/symbol identity, error location, actual validation
outcome and unresolved question. Long command output often has crucial diagnostics
at the end: a future extractor should preserve head/tail or structured diagnostics,
not blindly keep the first bytes. Summaries remain partial evidence.

Cache semantic classifications only with explicit validity keys: model version,
question version, goal/steering revision and evidence content hashes. Revalidate
on file changes. Never cache permission approval. Within one stable decision,
equivalent candidates can be grouped or evaluated for independent usefulness;
distinct useful alternatives should not be forced into a fictitious unique winner.

Confidence is derived from the returned distribution, not the probability that an
entire coding task will succeed. The documented Choice visualization computes
`confidence = (n * max_probability - 1) / (n - 1)` (clamped to 0–1). Thus the current
0.8 threshold corresponds to about 0.867 top probability with two candidates plus
insufficient-information, or 0.85 with three candidates plus that option. Always
record candidate count and the distribution when comparing confidence over time.

A future uncertainty policy could cool down only a repeated decision fingerprint
and allow Jev again after genuinely new evidence. Auth/transport failures can keep
the run-wide circuit breaker. That differs from simply retrying the same question
or disabling selection after every ambiguous ranking; it requires evaluation before
replacing the current immediate handoff policy.

## Evaluation needed before enabling new routing

Start with the existing 10-task `packages/evaluation/tasks/internal-v1.json` smoke
suite, then add realistic repo tasks, multilingual requests, overlapping valid
actions, long logs and missing evidence. The tiny synthetic pilot is not that suite.

Compare ordinary loop, current candidates, compact-state candidates, and retrieval
reranking on the same task revisions, primary model and permission mode. Use fresh
workspaces and multiple repetitions; randomize run order and report cache conditions.
Use isolated daemons/settings instead of changing the user's live desktop settings.

Collect all of these, including failed runs:

- Deterministic task pass rate, scope violations, regressions and repair attempts.
- Primary input/output/reasoning usage, cache reads/writes, compaction and auxiliary
  model usage; Jev inputs and requests separately. Avoid double-counting provider
  usage fields that already include reasoning or cached input.
- Total API cost per run, plus total spend across attempts divided by successful
  tasks. Include failed-attempt spend; a cheaper failure is not a better agent.
- End-to-end duration and Jev p50/p95, fallback rate, LLM turns, tool calls and
  repeated reads. SDK retries count toward both spend and wall-clock time.
- Retrieval recall of required evidence, precision at the retained token budget,
  and accuracy versus coverage for automatic decisions.

The existing evaluator does not yet aggregate Jev logs or all auxiliary usage into
its cost report. Extend it before treating its token total as a system-wide bill.
Use separately labelled development and held-out cases to choose risk-specific
thresholds. For overlapping valid actions, annotate acceptable sets rather than one
arbitrary “correct” ID. Shadow agreement with the LLM alone is not ground truth.

Economic condition: saved primary-model work and avoided repair work must exceed
candidate-generation overhead + extra primary context + Jev input cost + fallback
work. Cache-read pricing and end-to-end latency can change that outcome materially.
Keep ordinary behavior unless the new variant preserves the agreed quality target
and reduces cost per successful task or latency on the held-out evaluation.

## Sources checked on 2026-09-21

- [TypeSafe introduction](https://docs.typesafe.ai/introduction): atomic typed
  questions and independent questions evaluated against shared state.
- [How to build with TypeSafe](https://docs.typesafe.ai/concepts/how-to-build-with-system-one):
  keep deterministic control flow in code and make questions narrow.
- [Models](https://docs.typesafe.ai/models): `jev-latest` currently resolves to
  `jev-1.13.0`; $0.042/M input tokens, free output, text-only; 64k request budget
  and 32k state-plus-longest-question budget. These can change.
- [Confidence](https://docs.typesafe.ai/confidence): distribution-derived confidence
  and thresholds matched to consequences, calibrated on application data.
- [Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13): literal
  reading, numerical weakness, indirection, distractors and adversarial content.
- [Speculative fan-out](https://docs.typesafe.ai/patterns/fan-out): batch independent
  questions; software composes the results.
- [Skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion): staged
  catalogue ranking with an explicit no-match path; its published results are not
  results for this repository.
