<system-reminder data-role="deep-research-pending">
Reminder: the user invoked `/deep-research` earlier in this turn-chain and you have NOT yet called the **Workflow** tool.

You're allowed at most one short clarifying round (target audience / depth / sources / timeframe). Once you have a workable question, you MUST call:

- tool: `Workflow`
- name: `"deep-research"`
- args: `"<scoped question>"`  ← MUST be a plain string, NOT an object. Example: `args: "What is x.com?"`

Do NOT wrap the question as `{ "question": "..." }` — the tool's schema rejects objects. As soon as scope is clear, call the tool. Do NOT do the research yourself. Do NOT propose to start later.
</system-reminder>
