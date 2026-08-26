# CLAUDE.md

The current product runtime is TypeScript. The default daemon, Agent Loop, protocol contracts, CLI, and evaluation runner live under `packages/` (`protocol`, `runtime-ts`, `cli`, `evaluation`); the desktop workbench connects to the TypeScript daemon. This branch is TypeScript-only: the historical Python runtime lives on `main` and the `python-runtime` reference branches.

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

The Tauri + Vue desktop workbench and Node terminal client connect to the persistent TypeScript daemon (`npm run daemon`, 127.0.0.1:7438) over JSON-RPC 2.0 NDJSON. Shared contracts live in `packages/protocol`.

Keep new product behavior in `packages/runtime-ts`. Python scripts under `packages/runtime-ts/skills` are isolated helpers for artifact formats whose mature libraries are Python-first; they are external subprocess tools, not runtime dependencies.
