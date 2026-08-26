# TypeScript Runtime

This branch contains the TypeScript product runtime. The `packages/`
directory holds the npm workspaces:

- `protocol/` is the shared JSON-RPC, event and workflow contract.
- `runtime-ts/` is a Node.js daemon with TCP/NDJSON transport, an event bus,
  run lifecycle, workflow helpers, workspace boundary checks and a typed tool
  registry.
- `cli/` is the Node command-line client.
- `evaluation/` is the evaluation runner and reporting harness.

Run the current TypeScript checks from the repository root:

```powershell
npx tsc -p packages/protocol/tsconfig.json --noEmit
npx tsc -p packages/runtime-ts/tsconfig.json --noEmit
npx tsc -p desktop/tsconfig.json --noEmit
npx tsx --test packages/runtime-ts/tests/runtime.test.ts
```

Start the daemon on port `7438`:

```powershell
npm run --prefix packages/runtime-ts dev
```

The command-line entry point after a global install:

```powershell
sztu-ts core start
sztu-ts chat
```

From a source checkout, the equivalent scripts are `npm run cli -- ...` and
`npm run daemon`.

The runtime supports OpenAI-compatible and Anthropic providers, context
budgeting, session history, workspace tools, permissions, Git operations,
skills, MCP clients, subagents, and typed workflow orchestration. The
historical Python implementation lives on other branches of the repository
and is not part of this branch.
