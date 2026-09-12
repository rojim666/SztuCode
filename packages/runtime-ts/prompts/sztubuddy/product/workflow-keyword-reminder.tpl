<system-reminder data-role="workflow_keyword_request">
The user explicitly opted in to a Dynamic Workflow for this request
(via the `ultracode` keyword or a "use a workflow" phrase).

Recommended next step:
1) Decide whether the task genuinely benefits from many parallel sub-agents.
   - YES (codebase audit, large migration, multi-source research) → call the Workflow tool.
   - NO  (simple task, single-shot answer) → continue without a workflow.
2) If you call Workflow:
   - Prefer `script` for one-off orchestrations; reuse `name`/`scriptPath` for recurring patterns.
   - Remember the deterministic sandbox restrictions (no `Date.now`, `Math.random`, `new Date()`).
   - The tool returns immediately with a `runId`; the user can monitor progress via `/workflows`.
</system-reminder>
