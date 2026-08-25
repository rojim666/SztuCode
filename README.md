# SztuCode

SztuCode is a local-first, event-driven AI coding agent. The product runtime is
TypeScript: a Node daemon, a typed JSON-RPC protocol, a terminal CLI, and a
Tauri/Vue desktop workbench.

The historical Python daemon is isolated on the `python-runtime` branch and is
not part of the main product branch.

To inspect the Python runtime locally, switch to that branch explicitly:

```bash
git switch python-runtime
```

The branch is kept as a compatibility and validation reference; new daemon
features should be implemented on the TypeScript runtime first.

## Architecture

```text
Tauri desktop ─┐
Node CLI ───────┼─ TCP / NDJSON / JSON-RPC 2.0 ─ TypeScript daemon (7438)
Evaluation ────┘                                  │
                                                  ├─ sessions and workspaces
                                                  ├─ Agent Loop and tools
                                                  ├─ permissions and MCP
                                                  ├─ skills and subagents
                                                  ├─ context, memory and compaction
                                                  └─ events, traces and verification
```

The daemon can discover completion checks from `.sztu/checks.toml`. Set
`SZTU_REQUIRE_VERIFICATION=1` to enable independent checks and the bounded
repair loop. Verification commands run as argv subprocesses, with output and
workspace digests recorded under the run directory.

For example, a workspace can declare a completion check with:

```toml
[[check]]
id = "unit-tests"
command = ["npm", "test"]
priority = 10
```

Run verification-enabled work with:

```bash
SZTU_REQUIRE_VERIFICATION=1 npm run cli -- run --goal "修复测试失败"
```

## Quick Start

Requirements: Node.js 20+, npm, and an Anthropic or OpenAI-compatible API key.

```bash
git clone https://github.com/rojim666/SztuCode.git
cd SztuCode
npm install
npm run build
cp .env.example .env
```

Start the daemon and use the CLI from separate terminals:

```bash
npm run daemon
npm run cli -- ping
npm run cli -- run --goal "分析当前项目并修复测试失败"
npm run cli -- chat
```

The explicit aliases `npm run daemon:ts` and `npm run cli:ts` are equivalent.
The desktop workbench connects to the same TypeScript daemon:

```bash
cd desktop
npm install
npm run tauri dev
```

Do not commit `.env`; configuration details are in
[docs/getting-started/configuration.md](docs/getting-started/configuration.md).

## Project Layout

```text
packages/
  protocol/       JSON-RPC, event and workflow contracts
  runtime-ts/     daemon, Agent Loop, tools, permissions and extensions
  cli/            Node terminal client
  evaluation/     TypeScript evaluation runner
desktop/          Tauri 2 + Vue 3 workbench
scripts/          TypeScript build and maintenance scripts
docs/             usage, development and architecture documentation
```

## Development

```bash
npm run typecheck
npm test
npm run build
npm run build --prefix desktop
npm run docs:protocol
npm run docs:links
```

The daemon and client communicate over JSON-RPC 2.0 NDJSON. Protocol changes
belong in `packages/protocol`; runtime behavior belongs in
`packages/runtime-ts`.
