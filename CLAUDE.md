# CLAUDE.md

The current product runtime is TypeScript. The daemon, Agent Loop, protocol, CLI, evaluation runner, and desktop workbench live under `packages/` and `desktop/`. The historical Python runtime is isolated on the `python-runtime` branch.

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

The Tauri + Vue desktop workbench and Node terminal client connect to the TypeScript daemon (`npm run daemon`, 127.0.0.1:7438) over JSON-RPC 2.0 NDJSON. Shared contracts live in `packages/protocol`; runtime behavior belongs in `packages/runtime-ts`.

Keep new product behavior in TypeScript (`packages/runtime-ts`). Python scripts under `packages/runtime-ts/skills` are isolated helpers for artifact formats whose mature libraries are Python-first.
