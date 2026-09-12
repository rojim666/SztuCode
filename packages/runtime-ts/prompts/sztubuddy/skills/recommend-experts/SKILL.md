---
name: recommend-experts
description: |
  When a task needs professional judgment, deep research, a specialist role, or multi-role collaboration and no Expert is selected in the current session, search for real Experts or Expert Teams and recommend them with an inline card.
allowed-tools: search_plugins suggest_plugin_install
license: Internal
disable: false
---

# Recommend Experts

Use this Skill only when a specialist role or multi-role workflow would clearly improve the current task and no Expert is selected in the current session.

## Workflow

1. Confirm that no Expert is selected in the current session. If one is already selected, stop immediately; do not search, recommend, or replace it.
2. Call `search_plugins` with `type` set to `expert`. Put the user's request in `userIntent`; add `keywords` only when useful.
3. Match the current task against the curated scenarios and candidate descriptions. Candidates may be individual `expert` plugins or `expert_team` plugins; select at most three in total.
4. Every plugin ID must exactly match an `id` returned by this `search_plugins` call.
5. Call `suggest_plugin_install` exactly once to render one Expert card. If recommending multiple candidates, include all of them in this single call:

```json
{
  "type": "expert",
  "contextLabel": "For this deep-research task",
  "pluginId1": "DeepResearchExpert",
  "pluginId2": "GPTResearcherTeam"
}
```

## `suggest_plugin_install` Schema

Follow this schema exactly:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "type": {
      "type": "string",
      "enum": ["connector", "expert"]
    },
    "contextLabel": {
      "type": "string"
    },
    "pluginId1": { "type": "string" },
    "pluginId2": { "type": "string" },
    "pluginId3": { "type": "string" }
  },
  "required": ["type", "pluginId1"]
}
```

One call can recommend at most three candidates. Never pass arrays, `plugins`, `pluginIds`, or an `{ "item": ... }` wrapper.

## Rules

- Never invoke `suggest_plugin_install` more than once in the same response, whether sequentially or in parallel.
- A single `suggest_plugin_install` call can recommend one to three candidates by using `pluginId1`, `pluginId2`, and `pluginId3`.
- The user can enable only one Expert or Expert Team; never enable one silently or replace the current Expert.
- Do not replace the `suggest_plugin_install` card with a text list.
- If the search returns `expertAlreadySelected: true`, immediately continue the original task without recommending again.
- If the search returns no relevant results, silently continue the original task.
- After the user skips, times out, or cancels, do not recommend the same candidates again in the same response.
- Never use web search to find Plugins; `search_plugins` is the only source for candidates.
