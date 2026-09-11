# Ardot MCP Tool Usage Guide — Complete Reference

This document provides end-to-end workflow examples. For design rules, property constraints, troubleshooting, and the full **Tiered Validation / Convergence Threshold** spec, see `design-rules.md`.

> **Four reminders** before reading the examples:
> 1. **File-open gate** — `create_design` / `open_design` must complete and the ready context update must arrive **before** any other MCP call. Never bundle them with reads in the same message.
> 2. **`fetch_file_info` timing differs per branch**:
>    - `open_design` branch → call `fetch_file_info` right after the file is ready (before Step 1 reads).
>    - `create_design` branch → **defer** `fetch_file_info` until **after Step 5** (`build_style_guide`). Steps 2 - 5 are pure local reasoning / file reads / non-file MCP work, so they naturally cover the file's async load window. Fold `fetch_file_info` into the Step 6 parallel batch.
> 3. **Parallelize independent reads** — when a step contains multiple calls with no mutual data dependency, issue them in a single message as parallel tool calls; do not serialize them. The examples mark these with `(parallel, single message)`.
> 4. **Validation tiers** — `[T1]`/`[T3]`/`[T4]`/`[T5]` tags mark which validation tier applies to each `batch_edit`. Do **not** run full screenshot+layout after every batch. Cap corrective iterations at 2 per section.

## Ardot MCP Tool Usage Guide

## End-to-End Workflow Examples

### Example A: Creating a New Landing Page

```
Step 0 (message 1):
  create_design / open_design  ← exactly ONE call (follow <ardot_file_directive> if present); WAIT for ready before next message.
  (Never bundle subsequent reads into this same message — the editor is not loaded yet.)
  # open_design branch: fetch_file_info can follow in the next message (before Step 1 reads).
  # create_design branch: DO NOT call fetch_file_info yet — defer it to Step 6 below.

Step 1 — read existing state (skipped for fresh create_design):
  # Fresh file: empty canvas, root "0:1", no variables yet → nothing to read.
  # Opened existing file: call the following (parallel, single message):
  #   fetch_editor_state(includeSchema: false)
  #   fetch_variables

Step 2: Creative vs. Compositional → creative (new landing page) → continue to Step 3.

Step 3: Load references/guidelines-landing-page.md → learn landing page design rules
        (Local file reads — no MCP calls. This gives the create_design async load time to settle.)

Step 4: search_style_guide(topK: 3, styleKeywords: "modern minimal website", colorKeywords: "...", typographyKeywords: "...", layoutKeywords: "...")

Step 5: Review search_style_guide candidates → select best fit per domain
  build_style_guide(style: "...", color: 3, typography: "...", layout: "...")
  → receive complete design system

Step 6 (parallel, single message):
  # create_design branch: include fetch_file_info here (deferred from Step 0).
  # NOTE: this deferred call is fetch_file_info ONLY — the file was already created in Step 0.
  #       Do NOT call create_design again here.
  fetch_file_info                                                            # create_design branch only
  locate_available_space(width: 1440, height: 3000)

Step 7: batch_edit → page frame + hero scaffold (structural)      [T1]
        → capture_layout(heroId, problemsOnly: true)              (skip screenshot)
        batch_edit → hero content + styling (visual)              [T3]
        → capture_screenshot(nodeIds: [heroId])                   (skip layout)
        batch_edit → features section scaffold + content + style  [T4, section complete]
        → capture_screenshot + capture_layout(problemsOnly: true) (once)
        batch_edit → footer + CTA sections                        [T4, section complete]
        → capture_screenshot + capture_layout(problemsOnly: true) (once)
        IF any real issues accumulated → ONE batch_edit fixing all of them
        → re-run only the tier that flagged them
        (Max 2 fix iterations per section; ignore ≤4px spacing noise.)

Step 8: capture_screenshot(full page)                            [T5, final]
```

Notes:
- For a freshly created file this whole flow is **3 MCP round-trips** after `create_design` (Step 3 is a local file read; Step 4 `search_style_guide`, Step 5 `build_style_guide`, Step 6 parallel batch bundling `fetch_file_info` + `locate_available_space`) before the first `batch_edit`.
- For an opened existing file it's **4 MCP round-trips** (`fetch_file_info` after `open_design` + Step 1 parallel reads + Step 4 search + Step 5 build + Step 6 locate; search and build are inherently sequential since build depends on the search selection).
- Do not screenshot between T2 (pure content) or consecutive T3 batches — defer to the section boundary.
- Skip the in-Step-7 fix pass entirely if the T4 checks came back clean.

### Example B: Modifying an Existing Design

> Modify tasks are **non-generation** — Step 0 of `SKILL.md` is a no-op for this example. Go straight to the reads below.

```
Step 0: Ensure design file is open → skip if editor already has a file loaded
Step 1: fetch_editor_state(includeSchema: false) → check current state and selection
Step 2: batch_read(patterns: [{name: "Header"}]) → find target elements
Step 3: capture_layout(parentId: "headerId", maxDepth: 2) → mandatory pre-flight layout check
        If any child reports "Outside parent bounds":
          → parent is too small for existing + incoming children. Switch parent to HUG: {height: "hug_contents"}.
          → Do NOT calculate or set a numeric height — let the engine size it from children.
        If no overflow → parent has enough space; keep existing sizing, no change.
Step 4: batch_edit → apply the change from Step 3 + insert modifications (≤25 ops)
Step 5: capture_layout(parentId: "headerId", maxDepth: 2) → mandatory post-flight verify
```

### Example C: Global Style Update

```
Step 0: Ensure design file is open → skip if editor already has a file loaded
Step 1: fetch_editor_state(includeSchema: false) → check current state
Step 2: scan_all_unique_properties(parentIds: ["rootFrame"]) → audit existing styles
Step 3: substitute_all_matching_properties → bulk update matching properties
Step 4: capture_screenshot → verify the global changes            [T3]
        (No capture_layout — substitutions don't change structure.)
```

### Example D: Setting Up Design Tokens

```
Step 0: Ensure design file is open → skip if editor already has a file loaded
Step 1: fetch_editor_state(includeSchema: false) → check current state
Step 2: fetch_variables → inspect existing variables
Step 3: apply_variables → create or update variable sets with Light/Dark modes
Step 4: batch_read(patterns: [{reusable: true}]) → find components to bind variables to
Step 5: batch_edit → bind variable references to component properties   [T2]
        (Token binding alone doesn't change visuals or structure — skip validation.
         If a subsequent visual batch follows, validate there instead.)
```

### Example E: Creating a Registration Form

```
Step 0: Ensure design file is open → create_design / open_design if needed, wait for ready
        (open_design branch: follow with fetch_file_info; create_design branch: defer fetch_file_info — for a fresh file Step 1 is skipped, so fold it into the message that issues the first batch_edit below)
Step 1: fetch_editor_state(includeSchema: false) → get available components
Step 2: batch_edit → container frame + title + inputs in ONE batch   [T4 small form]
  container=I("pageId", {type: "frame", name: "Registration", layout: "vertical", width: 400, height: "hug_contents(600)"})
  title=I("containerId", {type: "text", name: "Title", content: "Create Account", fontSize: 28, fill: "#18191C"})
  input1=I("containerId", {type: "ref", ref: "InputComponentId"})
  U(input1+"/label", {content: "First Name"})
  ... (remaining fields, submit button, all in the same batch_edit)
Step 3: capture_screenshot + capture_layout(problemsOnly: true)      (once)
Step 4: IF issues → ONE batch_edit fixing all → re-run same tier (max 2 iterations)
```

Notes:
- Small self-contained UIs like a form should be built in **one** batch when ≤25 ops allow, then validated once — not scaffolded, content-filled, and styled in separate round-trips.

