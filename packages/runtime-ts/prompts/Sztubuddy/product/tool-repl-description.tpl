Execute JavaScript to orchestrate a task, with programmatic access to capability bridges. Supports top-level await. State persists across calls within the session (variables, imported bridges) — like a notebook kernel.

Surface a result by returning it (`return x`) or leaving it as the last expression — like a notebook kernel. To show an image, return an image value `{ $media: "image/png", data: <base64-or-data-url> }`, or an array mixing text and images (e.g. `return [summary, screenshot]`). Use `nodeRepl.write(text)` for additional text output.

## Capability bridges

Capabilities (browser control, computer use, …) are provided as importable bridges, NOT as separate tools. Import a bridge, then read its documentation before using it:

```js
const { browser } = await import("@wb/browser");
nodeRepl.write(await browser.documentation());   // ALWAYS read this first, in full
```

The set of available bridges is provided by the host and may change; if an import throws "not available", that bridge is not offered in this session. You cannot import arbitrary Node modules (`node:fs`, npm packages, …) — only host-provided bridges.

## When to use

Prefer the REPL when a task needs several capability calls composed with control flow (loops, conditionals, waiting, retry) in one turn — e.g. driving a browser through a multi-step flow — instead of one model round-trip per action. For a single one-off action, call the relevant tool directly.

Each bridge call is subject to the same permission checks as any tool. Keep scripts focused; long-running scripts are bounded by `timeout` (default 30s, max 600s).
