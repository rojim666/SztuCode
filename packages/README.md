# TypeScript Runtime

## Runtime Composition

`packages/runtime-ts` is the daemon composition entry point. `RuntimeServer`
assembles the TCP/NDJSON transport, trace writer, event bus, provider, and
coding-agent services. RPC behavior lives in `ServerService`; it creates and
opens transport-free `AgentSession` handles. `RunManager` remains as a
compatibility runner for existing CLI, desktop, and test callers while new
composition code should use `ServerService` and `AgentSession`.

Workspace, permission, MCP, skills, Git, settings, and model services are
constructed once by the entry point and injected into the service graph. The
daemon still defaults to `127.0.0.1:7438`, keeps the existing JSON-RPC/NDJSON
methods and event names, and can be started with:

```powershell
npm run --prefix packages/runtime-ts dev
```

The dependency direction is `RuntimeServer -> ServerService -> coding-agent
services`; transport and desktop clients depend only on the protocol and
daemon client packages.

The repository keeps separate TypeScript and Python runtime entry points. This
directory contains the TypeScript packages:

- `protocol/` is the shared JSON-RPC, event and workflow contract.
- `server/` contains the reusable TCP/NDJSON transport, handshake, RPC router,
  and live `SessionRuntime` attachment layer.
- `client/` contains the typed daemon client SDK with handshake, request
  correlation, timeouts, reconnect, and event subscriptions.
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

# Python CLI/runtime (default port 7437)
sztu-py core start
sztu-py chat
```

From a source checkout, the equivalent scripts are `npm run cli:ts -- ...`,
`npm run daemon:ts`, `npm run cli:py -- ...`, and `npm run daemon:py`. The
Python source scripts use the locked `uv` environment.

The runtime keeps the same JSON-RPC envelope and supports
OpenAI-compatible and Anthropic providers, context budgeting, session history,
workspace tools, permissions, Git operations, skills, MCP clients, subagents,
and typed workflow orchestration. The Python implementation remains available
under `py-runtime/src/sztu_code` and uses its own CLI command and default port.
