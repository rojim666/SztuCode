---
name: recommend-connectors
description: |
  When a user task requires an external app, service, API, MCP server, authorization, or third-party data and no connected tool covers it, search for real Connectors and recommend them with an inline card.
allowed-tools: search_plugins suggest_plugin_install
license: Internal
disable: false
---

# Recommend Connectors

Use this Skill only when the current task directly requires an external service, authorization, or the user's third-party data and the available tools cannot complete it.

## Workflow

1. Call `search_plugins` with `type` set to `connector`. Put the user's request, verbatim or lightly paraphrased, in `userIntent`; add `keywords` only when useful.
2. Keep only candidates that directly help with the current task and are still disconnected in the search results.
3. Select at most three candidates. Every plugin ID must exactly match an `id` returned by this `search_plugins` call; never guess or rewrite an ID.
4. Call `suggest_plugin_install` exactly once to render one Connector card. If recommending multiple candidates, include all of them in this single call:

```json
{
  "type": "connector",
  "contextLabel": "For your code repositories",
  "pluginId1": "github",
  "pluginId2": "gitlab"
}
```

## Rules

- Never invoke `suggest_plugin_install` more than once in the same response, whether sequentially or in parallel.
- A single `suggest_plugin_install` call can recommend one to three candidates by using `pluginId1`, `pluginId2`, and `pluginId3`.
- Never install, connect, or authorize a Connector directly; every action must be initiated by the user from the card.
- Do not replace the `suggest_plugin_install` card with a text list.
- If the search returns no relevant results, silently continue the original task without describing the internal search process.
- After the user skips, times out, or cancels, do not recommend the same candidates again in the same response.
- Never use web search to find Plugins; `search_plugins` is the only source for candidates.
