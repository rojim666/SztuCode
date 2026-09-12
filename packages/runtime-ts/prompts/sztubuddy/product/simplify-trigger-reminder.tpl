<system-reminder data-role="simplify-trigger">
The user invoked `/simplify`{{target}} to clean up changed code.

You are improving the quality of the changed code, not hunting for bugs. Review
it for reuse, simplification, efficiency, and altitude issues, then fix what you
find. Do not look for correctness bugs — that is what `/code-review` is for.

Run `git diff` (or `git diff HEAD` if there are staged changes) to see what
changed. If there are no git changes, review the most recently modified files
that the user mentioned or that you edited earlier in this conversation.

## Phase 1 — Review (4 cleanup agents in parallel)

Launch **4 independent review agents** via the Agent tool, all in a
single message so they run concurrently. Pass each agent the diff and one of
the four angles below. Each returns its findings with `file`, `line`, a
one-line `summary`, and the concrete cost (what is duplicated, wasted, or
harder to maintain).

### Reuse

For each change:

1. **Search for existing utilities and helpers** that could replace newly written code. Look for similar patterns elsewhere in the codebase — common locations are utility directories, shared modules, and files adjacent to the changed ones.
2. **Flag any new function that duplicates existing functionality.** Suggest the existing function to use instead.
3. **Flag any inline logic that could use an existing utility** — hand-rolled string manipulation, manual path handling, custom environment checks, ad-hoc type guards, and similar patterns are common candidates.

### Simplification

Review the same changes for over-complicated patterns:

1. **Redundant state**: state that duplicates existing state, cached values that could be derived, observers/effects that could be direct calls
2. **Parameter sprawl**: adding new parameters to a function instead of generalizing or restructuring existing ones
3. **Copy-paste with slight variation**: near-duplicate code blocks that should be unified with a shared abstraction
4. **Leaky abstractions**: exposing internal details that should be encapsulated, or breaking existing abstraction boundaries
5. **Stringly-typed code**: using raw strings where constants, enums (string unions), or branded types already exist in the codebase

### Efficiency

Review the same changes for efficiency:

1. **Unnecessary work**: redundant computations, repeated file reads, duplicate network/API calls, N+1 patterns
2. **Missed concurrency**: independent operations run sequentially when they could run in parallel
3. **Hot-path bloat**: new blocking work added to startup or per-request/per-render hot paths
4. **Unnecessary existence checks**: pre-checking file/resource existence before operating (TOCTOU anti-pattern) — operate directly and handle the error
5. **Memory**: unbounded data structures, missing cleanup, event listener leaks
6. **Overly broad operations**: reading entire files when only a portion is needed, loading all items when filtering for one

### Altitude

Review the same changes for altitude (abstraction level) issues:

1. **Unnecessary comments**: comments explaining WHAT the code does (well-named identifiers already do that), narrating the change, or referencing the task/caller — delete; keep only non-obvious WHY (hidden constraints, subtle invariants, workarounds)
2. **Wrong abstraction level**: mixing high-level orchestration with low-level details in the same function
3. **Naming**: variables, functions, or types whose names don't match what they actually do

## Phase 2 — Apply the fixes

Wait for all four agents to complete, dedup findings that point at the same
line or mechanism, and fix each remaining one directly. Skip any finding whose
fix would change intended behavior, require changes well outside the reviewed
diff, or that you judge to be a false positive — note the skip rather than
arguing with it. Finish with a brief summary of what was fixed and what was
skipped (or confirm the code was already clean).
</system-reminder>
