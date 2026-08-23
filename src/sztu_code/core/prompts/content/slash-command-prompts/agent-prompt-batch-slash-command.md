# Batch: Parallel Work Orchestration

## Phase 1: Research and Plan (Plan Mode)
1. Understand the scope by launching Explore agents for independent research.
2. Decompose the work into 5-30 independent units with explicit ownership.
3. Determine the end-to-end test recipe and shared success criteria.
4. Write a plan that records dependencies, sequencing, and integration points.
5. Request approval before starting implementation.

## Phase 2: Spawn Workers (After Plan Approval)
Spawn one background agent per independent work unit using an isolated worktree.
Launch independent workers together so they can run concurrently. Give every
worker a self-contained prompt, allowed scope, expected output, and verification
command. Do not assign overlapping files without an explicit integration owner.

## Phase 3: Track Progress
Track every worker until it completes or needs attention. Maintain a compact
status table containing the work unit, owner, state, result, and integration
status. Validate each result before merging it into the shared outcome, resolve
conflicts deliberately, and run the agreed end-to-end test recipe after
integration.
