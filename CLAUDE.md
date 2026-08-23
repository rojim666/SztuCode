# CLAUDE.md

The current product runtime is Python. The default daemon, Agent Loop, bus protocol, CLI, and evaluation runner live under `src/sztu_code`. The TypeScript chain (`packages/`, `desktop/`) remains available via `npm run daemon:ts` / `npm run cli:ts`; the desktop workbench connects to the TypeScript daemon.

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

The Tauri + Vue desktop workbench and Node terminal client connect to the TypeScript daemon (`npm run daemon:ts`, 127.0.0.1:7438) over JSON-RPC 2.0 NDJSON; the default `npm run daemon` / `npm run cli` start the Python daemon (`src/sztu_code`, 127.0.0.1:7437). Shared TS contracts live in `packages/protocol`; Python bus contracts live in `src/sztu_code/core/bus`.

Keep new product behavior in Python (`src/sztu_code`). Python scripts under `packages/runtime-ts/skills` are isolated helpers for artifact formats whose mature libraries are Python-first.
