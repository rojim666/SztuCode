# TypeScript Packages

## Runtime Composition

`packages/runtime-ts` is the TypeScript daemon composition entry point.
`RuntimeServer` assembles transport, telemetry, EventBus, providers and
coding-agent services. `ServerService` owns RPC-facing application operations
and creates/opens transport-free `AgentSession` handles. `RunManager` remains a
compatibility runner for existing CLI, desktop and test callers; new runtime
code should use `ServerService` and `AgentSession`.

Workspace, permission, MCP, skills, Git, settings, and model services are
constructed once by the entry point and injected into the service graph. The
daemon still defaults to `127.0.0.1:7438`, keeps the existing JSON-RPC/NDJSON
methods and event names, and can be started with:

```powershell
npm run --prefix packages/runtime-ts dev
```

The dependency direction is:

```text
@sztucode/cli / desktop
          -> @sztucode/client -> @sztucode/protocol
@sztucode/runtime-ts -> @sztucode/server
                      -> @sztucode/protocol
                      -> @sztucode/session-fs
                      -> @sztucode/agent-core -> @sztucode/ai
                      -> @sztucode/telemetry
```

Clients depend on contracts and client transport only. The reusable server
transport owns generic wire/connection types and deliberately does not import
the protocol package; `runtime-ts` supplies protocol handlers when composing
the daemon. The server package does not create an AgentLoop; it accepts
`SessionRuntime`/`PiSessionRuntime` implementations through its service
boundary. The runtime composition layer injects workspace, permission, MCP,
skills, Git, settings, model and session services.

## Package responsibilities

The repository keeps separate TypeScript and Python runtime entry points. The
TypeScript packages have these boundaries:

- `ai/` contains provider-neutral model and streaming types used below the
  daemon boundary.
- `agent-core/` contains reusable agent/tool primitives; it does not own the
  daemon socket or desktop protocol.
- `protocol/` is the shared JSON-RPC, NDJSON, event, session and workflow
  contract, including wire validation and generated protocol documentation.
- `session/` defines session headers, entries, branches and backend interfaces.
- `session-fs/` implements the local JSONL session backend and the legacy
  directory adapter/migration path.
- `server/` contains reusable TCP/NDJSON transport, hello handshake, RPC
  router, connection state and live session attach/detach management.
- `client/` contains the typed daemon client SDK: hello, request IDs,
  idempotency keys, timeouts, reconnect, event subscriptions and typed session
  calls. It cannot call tools or models directly.
- `telemetry/` provides spans, child spans, attributes, events, status/error,
  no-op and in-memory adapters, plus the TraceWriter-compatible adapter.
- `runtime-ts/` is the Node daemon composition layer. It wires providers,
  EventBus, workspace/permission/MCP/skills/Git services, extensions,
  `ServerService`, `AgentSession` and the compatibility `RunManager`.
- `cli/` is a Node client of the daemon; it starts the bundled daemon when
  requested but does not implement Agent execution itself.
- `evaluation/` contains TypeScript evaluation runners and reports.

## Agent, Session and Server boundaries

- **Agent** (`AgentLoop`, tools and provider adapters) performs model turns,
  validates tool input, requests permission and publishes run events. It does
  not own sockets.
- **Session** (`AgentSession`, `SessionRuntime`, `session` interfaces and
  backends) owns one conversation's model context, lifecycle, snapshots,
  branching and persistence. A child/subagent receives its own session runtime.
- **Server** (`@sztucode/server` plus runtime `RuntimeServer`/
  `ServerService`) owns connections, handshake, routing, attachment and event
  delivery. It asks an injected session service to create/open sessions and
  never constructs an AgentLoop in the transport package.

## Connection and compatibility flow

1. A client opens TCP to `127.0.0.1:7438` (or the configured host/port).
2. A new client sends a `hello` frame with protocol version and capabilities;
   the daemon replies with `hello` or `hello_error` and a connection ID.
3. The client subscribes with `event.subscribe`, then sends JSON-RPC requests
   carrying a request ID and, for safe retries, an idempotency key.
4. The daemon routes the request, returns its JSON-RPC response and pushes
   subscribed events as `{ kind: "event", event }` NDJSON frames.
5. On disconnect, an idle attachment may be released while a running session
   remains alive; a new client can reconnect, attach and hydrate from snapshot
   plus event/history state.

`runtime-ts` runs the transport in compatibility mode. A legacy client may send
its first JSON-RPC frame without hello; the daemon keeps the old envelope,
method names, event names and error codes. New clients still use hello. This is
an in-process migration bridge, not a second protocol or a CBOR transport.

## Persistence and extensions

The current compatibility RPC path persists session metadata and visible
messages under `${SZTU_DATA_DIR:-~/.sztu}/sessions/<session_id>/` (`meta.json`,
`thread.jsonl`, context, notes and run event files). The compositional
`AgentSession` path uses `@sztucode/session-fs` JSONL files with a typed session
header, append-only entries, branch/fork metadata and atomic writes; it can
read/migrate the legacy directory format. Treat both locations as local
conversation data and do not commit them.

Extensions are loaded by the daemon, never by the client socket. Paths in
`SZTU_EXTENSIONS` are loaded as **global** extensions; paths in
`SZTU_WORKSPACE_EXTENSIONS` are loaded as **workspace** extensions. Workspace
extensions are visible only for their resolved workspace root. Modules export
`default activate(api)`, `extension`, or `activate`; load, activation, hook and
registration failures are recorded as diagnostics, and hook failures are
isolated from the daemon loop.

## Checks and local run

Run the current TypeScript checks from the repository root:

```powershell
npm run typecheck
npm test
npm run test:e2e:ts
npm run test:migration
npm run build --prefix desktop
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
and typed workflow orchestration. Subagents, workflow DAG execution, extension
APIs and the new `AgentSession` composition are still experimental in the
0.x line; their protocol fields and persistence details may change. The
Python implementation remains available under `py-runtime/src/sztu_code` and
uses its own CLI command and default port.
