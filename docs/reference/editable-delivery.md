# Editable delivery: implementation and current boundaries

The desktop attaches files to a workspace. Receiving a format does not imply that a compatible transcription, rendering, or generation model is installed.

## Exact text editing in the Python runtime

`edit_file` preserves UTF-8 BOM and original newline bytes outside the exact replacement. Empty selections are rejected. The optional `expected_hash` is the SHA-256 of the complete file at selection time; stale selections are rejected. Each edit persists both original and resulting bytes under `.sztu/file-versions` before replacing the file.

`file_history` lists versions for `path`. Supplying `version` and `expected_hash` restores the selected file contents under workspace-write permissions. Restoration creates another revision, so it can also be undone. Missing or corrupt snapshots and intervening edits fail instead of overwriting the current content. This is text/file-level editing, not a universal visual element selector. External processes do not participate in the runtime's mutation lock.

## Artifact versions in the desktop TypeScript daemon

New `artifact.register` calls save immutable content snapshots. `artifact.restore` requires `workspace_id`, `artifact_id`, `version`, and `expected_hash`. It captures the current file before restoring and resets verification to `unverified`. Legacy records without snapshots cannot recover already overwritten bytes. Registration is explicit; file edits performed outside this pipeline are not automatically versioned.

## Python Smart routing

Opt-in TOML configuration:

```toml
[llm]
router = "smart"
default_model = "your-configured-standard-model"
flagship_model = "your-configured-flagship-model"
```

Both models must be available through the configured provider and endpoint. The initial implementation uses request length and task signals to choose the standard or flagship model. It keeps the selected model for subsequent tool steps in the same run, and reports `smart:standard` or `smart:flagship` in model-selection events. This is rule-based complexity routing, not a price-aware budget optimizer, and does not change desktop TS routing. Users must supply actual model identifiers; none is silently chosen.

## Remaining work

- A selection contract across HTML, office documents, images, audio/video timelines and 3D scenes, with adapters that enforce the selected edit boundary.
- Desktop version history and restoration controls wired to actual snapshots.
- Price-aware routing and budget admission across model profiles, with capability checks and measured cost reporting.
- Automatic Harness/Agent/Skill matching and resource-aware parallel scheduling.
- Browser interaction acceptance tests generated from task requirements and tied to final artifact verification.
- Measured same-session and cross-session cache statistics. No fixed 99% or 95% cache hit claim is established by this implementation.
