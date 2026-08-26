# Session filesystem backend

`JsonlSessionBackend` stores one append-only JSONL file per session under the
configured root (`<root>/<session-id>.jsonl`). The first row is a versioned
`SessionHeader`; subsequent rows are typed entries with a sequence and parent
entry ID. Appends are serialized per session and forks are written through a
temporary file followed by `rename`, so a complete entry is never partially
visible.

Existing SztuCode sessions under `~/.sztu/sessions/<id>/` remain readable. The
legacy reader maps `meta.json` to a `SessionHeader`, `thread.jsonl` to a linked
message history, and an available `context.json` to a model-context entry. It
does not delete or alter the legacy directory. Call
`backend.migrateLegacy(id)` to atomically create the new JSONL file; migration
is repeatable and the old files remain as the rollback source.

An incomplete final line (a typical process-crash tail) is ignored and exposed
through `recoveryWarnings`. A malformed line before the end, an unknown entry,
missing parent, non-monotonic sequence, or duplicate ID is a hard validation
error. `SessionStoreBackendAdapter` provides the new `SessionBackend` shape on
top of the existing runtime `SessionStore` while the runtime continues using
its original APIs and files.
