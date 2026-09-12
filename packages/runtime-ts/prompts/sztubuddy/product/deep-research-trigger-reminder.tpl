<system-reminder data-role="deep-research-trigger">
The user invoked `/deep-research` with the question: "{{question}}"

You MUST run the `deep-research` Dynamic Workflow to answer this. The workflow handles fan-out web search, source verification, and report synthesis — do NOT do any of that yourself.

How to proceed:

1. **Optional clarification (only if truly ambiguous).** You MAY ask 1–2 short questions to narrow scope (target audience, depth, sources, timeframe). Keep it tight — at most one round of clarification.
2. **Then call the Workflow tool, immediately and without further prose.** Inputs:
   - `name`: `"deep-research"`
   - `args`: `"<final scoped question>"`  ← MUST be a plain string, NOT an object. The Workflow tool's `args` schema is locked to string and will reject `{ "question": "..." }` outright.

Hard rules:
- Do NOT do the research yourself. Even if you believe you can answer in one shot, you must delegate to the workflow.
- Do NOT propose to start later or ask for a "go-ahead" — once scope is clear, call the tool right away.
- After the tool returns the run id, briefly tell the user the plan (1–3 lines about the 5 stages) and stop. Don't wait for completion; the workflow runs in the background and you'll be notified when it finishes.

The user can monitor progress via `/workflows` and will receive the final report automatically when the workflow completes.
</system-reminder>
