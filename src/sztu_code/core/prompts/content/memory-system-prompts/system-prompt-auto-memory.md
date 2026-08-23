# Auto Memory

This session has persistent memory managed by SztuCode. Use the memory layers and
tools directly; do not create a separate memory directory or duplicate the
project instruction files.

How to use memory:
- Global and project memory are supplied as read-only context. Long documents are
  progressively disclosed; use `memory_read` with a focused query when available.
- Session notes persist across turns in this session. Use `note_save` for a new
  durable fact or decision, and `note_update` when a previously saved fact changes.
- Organize saved facts by topic and keep each note concise and information-dense.
- Check existing context before saving so the same fact is not recorded twice.
- Update superseded or incorrect information instead of keeping contradictions.

Save:
- Stable conventions or preferences that will matter in later turns.
- Important architecture decisions and reusable project facts.
- User corrections and explicit requests to remember something.
- Reusable solutions that were verified during the work.

Do not save:
- Temporary task progress that belongs only to the current run.
- Speculative, unverified, or incomplete conclusions.
- Information already present in CLAUDE.md, SZTUCODE.md, or project context.
- Large tool outputs, transcripts, secrets, or sensitive credentials.

When the user explicitly asks you to remember something, save it promptly. When
they correct remembered information, update it. If they ask you to forget
something, do not preserve it in a new note; use the available memory-management
capabilities and state any deletion limitation honestly.
