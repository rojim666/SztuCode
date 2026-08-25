# AGENT.md

> Current product path: TypeScript. The daemon, Agent Loop, protocol, CLI, and desktop workbench live under `packages/` and `desktop/`. The historical Python runtime is isolated on the `python-runtime` branch.

## Commands

```bash
npm install
npm run typecheck
npm test
npm run build
npm run build --prefix desktop
npm run docs:protocol
npm run docs:links
npm run daemon
npm run cli -- ping
```

## Architecture

The default kernel is the TypeScript daemon (`packages/runtime-ts`, 127.0.0.1:7438); `npm run daemon` and `npm run cli` use it. The Tauri desktop workbench and Node terminal client connect over JSON-RPC 2.0 NDJSON.

```
packages/runtime-ts (daemon)
  └─ 127.0.0.1:7438
       ↑ JSON-RPC 2.0 NDJSON
packages/cli   desktop (Tauri + Vue)
```

Shared request, response, event, and workflow types live in `packages/protocol`. Runtime behavior belongs in `packages/runtime-ts`; do not add product contracts to external scripts or generated files. The desktop application is the primary user-facing surface and must be built after UI changes.

## TypeScript conventions

- Keep public RPC parameters and results typed in `packages/protocol`.
- Prefer discriminated unions for protocol state and event handling.
- Keep filesystem and workspace boundaries in runtime helpers; never accept an unchecked path from an RPC request.
- Add focused tests for permission, session, persistence, provider, and error-path changes.
- Use Node built-ins and existing workspace dependencies before adding a package.
- Comments should explain non-obvious constraints, not restate code.

## Python boundary

The Python daemon is maintained only on the `python-runtime` branch. Python files under `packages/runtime-ts/skills` are isolated subprocess helpers for individual skills and are not daemon, CLI, protocol, or desktop behavior.

## Documentation

Current user, contributor, architecture, testing, and operations documentation lives in `docs/`; historical proposals are under `docs/archive/` and do not define current behavior. Protocol documentation is generated with `npm run docs:protocol`.
