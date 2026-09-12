# Sztubuddy Prompt Integration

SztuCode packages the complete local Sztubuddy prompt collection in both runtimes.
The source collection is needed only for re-importing, not for running the application.

## Resource Layout

The two installed copies are `packages/runtime-ts/prompts/Sztubuddy/` and
`py-runtime/src/sztu_code/core/prompts/Sztubuddy/`. Each contains 485 original files:

- `main/`: 15 main prompt templates.
- `styles/`: 7 response styles.
- `modes/`: Ask, Craft, Plan and Expert fragments, with their original manifests.
- `skills/`: 295 files, including 48 recursively discovered `SKILL.md` entries and references.
- `product/`: 118 product templates for commands, tools, compaction, memory and workflows.
- `agents/`: 19 built-in agent definitions, resolved to their product templates at runtime.

`manifest.json` records the original source paths and SHA-256 hashes, skills, agents,
command entries and tool-name mappings. Original resources are preserved unchanged.
`runtime-contract.md` describes SztuCode's actual tool and permission boundaries.

## What Runs

The default system prompt uses `main/Sztubuddy-prompt.tpl`, Craft execution fragments,
the efficient style and the SztuCode runtime contract. The TypeScript Nunjucks renderer
and Python sandboxed Jinja renderer normalize the source template dialect and resolve
variables before model invocation. Product-only UI sections are omitted from the base.
Plan permissions add Plan guidance through the existing prompt harness. Ask and Expert
fragments and alternative styles are available as resources; this migration does not
add new mode/style selectors to the desktop UI.

The original `prompts/content/` IDs remain as compatibility entry points for the prompt
catalog and its existing consumers. Their Markdown content is generated from the new
collection or from the host protocol where the source has no equivalent. They are not
an independent old prompt set. Native planner, executor, reviewer and tester profiles
use Sztubuddy templates while retaining SztuCode tool limits and workflow JSON contracts.

Skills are listed with metadata and loaded by the `skill` tool only when needed. Their
reference files are read with `prompt_resource`; relative reference links are resolved
against the reported bundle-relative skill directory. Skill code examples are not
interpreted as prompt templates. Personal and workspace skills still override built-ins.
Disabling the winning skill does not activate an older fallback with the same name.

Five imported skill groups appear as built-in plugins: `sheetagent`, `tencent-docs-plugin`,
`tencent-docx`, `tencent-pptx` and `weixinpay`. Plugin switches disable their imported skills.
Existing host skills with executable scripts remain available where no imported skill
replaces their name.

Seven product workflows are exposed through the skill/command path: `/commit`,
`/create-pr`, `/security-review`, `/insights`, `/statusline`, `/init` and `/loop`.
These are prompt workflows. For example, `/loop` requires an actual scheduling tool;
loading its prompt does not create a scheduler. Templates containing shell snippets
prefixed with `!` do not execute those snippets during rendering. The agent must collect
the real facts with registered tools.

The 19 source agents are available to `spawn_agent`. Explore and Plan use plan permissions.
An explicit empty tool list means no tools. Applying a skill cannot expand an imported
agent's tool whitelist. Existing workflow role names remain supported.

## Inspecting The Active Prompt

The `context.injected` event contains the actual system prompt supplied to the model,
including rendered Sztubuddy base instructions. TypeScript child sessions now receive
role instructions as a system message, and Python child runs emit their system prompt
as well. Dynamic workspace and skill metadata remains in the turn's reminder. Skill
bodies appear when invoked; the full 485-file collection is never injected every turn.

Use `prompt_resource` with `{ "path": "product/", "offset": 0, "limit": 20 }` to browse
product resources. A file path returns a rendered excerpt with line-based pagination;
a category returns file-based pagination. Absolute paths and traversal are rejected.

## Updating And Packaging

From the repository root:

```powershell
node scripts/import-Sztubuddy.mjs "F:\Learning\codinganget\prompts-合集"
npm run build --workspace @sztucode/runtime-ts
uv run --project py-runtime pytest py-runtime/tests/unit/test_Sztubuddy.py
```

The importer regenerates both bundles, indexed content, native role template references
and the four legacy command skills. Edit the importer when changing generated mappings.
Edit the resource loaders when changing runtime composition. Restart the daemon after
changing prompts because templates and catalog entries are cached per process.

The desktop runtime packaging step copies the complete `prompts/` tree. Python wheels
include the resource directory inside `sztu_code`. Installed desktop builds require a
runtime rebuild/repackage before the changes are visible.

## Capability Limits

This collection contains prompt and reference text, not Sztubuddy's service implementations.
Tencent document/payment connectors, generation services, missing scripts/assets and other
upstream tools are not installed by importing their instructions. Registered tools, their
schemas and runtime permission checks remain authoritative. Sztubuddy documentation is
upstream reference material, not evidence that SztuCode implements an upstream feature.

The source compaction template's blanket claim that all tasks are completed is adapted
to preserve pending work and next actions. Local memory formats and workflow JSON outputs
retain the host contracts consumed by the existing runtime.
