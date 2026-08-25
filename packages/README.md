# TypeScript Runtime

The repository's product runtime is TypeScript. This directory contains the
runtime packages:

- `protocol/` is the shared JSON-RPC, event and workflow contract.
- `runtime-ts/` is a Node.js daemon with TCP/NDJSON transport, an event bus,
  run lifecycle, workflow helpers, workspace boundary checks and a typed tool
  registry.

Run the current TypeScript checks from the repository root:

```powershell
npx tsc -p packages/protocol/tsconfig.json --noEmit
npx tsc -p packages/runtime-ts/tsconfig.json --noEmit
npx tsc -p desktop/tsconfig.json --noEmit
npx tsx --test packages/runtime-ts/tests/runtime.test.ts
```

Start the TypeScript daemon on port `7438`:

```powershell
npm run --prefix packages/runtime-ts dev
```

The command-line entry points are intentionally distinct:

```powershell
# TypeScript CLI/runtime (default port 7438)
sztu-ts core start
sztu-ts chat
```

From a source checkout, the equivalent scripts are `npm run cli -- ...` and
`npm run daemon` (or the explicit `:ts` aliases).

The runtime uses a JSON-RPC envelope and supports
OpenAI-compatible and Anthropic providers, context budgeting, session history,
workspace tools, permissions, Git operations, skills, MCP clients, subagents,
and typed workflow orchestration. The historical Python implementation is
maintained separately on the `python-runtime` branch.
