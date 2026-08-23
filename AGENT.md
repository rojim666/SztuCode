# AGENT.md

> Current product path: Python. The default daemon, Agent Loop, bus protocol, CLI, and evaluation runner live under `src/sztu_code`. The TypeScript chain (`packages/`, `desktop/`) remains available via `npm run daemon:ts` / `npm run cli:ts`; the desktop workbench connects to the TypeScript daemon.

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

The default kernel is the Python daemon (`src/sztu_code/core`, 127.0.0.1:7437); `npm run daemon` and `npm run cli` use it. The Tauri desktop workbench and the Node terminal client (`npm run daemon:ts` / `npm run cli:ts`) connect to the persistent TypeScript daemon (`packages/runtime-ts`, 127.0.0.1:7438) over JSON-RPC 2.0 NDJSON.

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

Python is the default product runtime. Keep new product behavior in `src/sztu_code` with focused pytest coverage. The Skill directories under `packages/runtime-ts/skills` with Python scripts are isolated subprocess tools and must not define daemon, CLI, protocol, or desktop behavior for the Python chain.

## Documentation

Current user, contributor, architecture, testing, and operations documentation lives in `docs/`; historical proposals are under `docs/archive/` and do not define current behavior. Protocol documentation is generated with `npm run docs:protocol`.
