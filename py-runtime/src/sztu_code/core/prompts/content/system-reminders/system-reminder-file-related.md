# File-related reminders

<system-reminder>Warning: the file exists but is empty.</system-reminder>

<system-reminder>
The file was modified, possibly by the user or a formatter. Re-read the current
contents before making decisions; do not assume the earlier snapshot is still
valid.
</system-reminder>

<system-reminder>The file display was truncated at line N.</system-reminder>

<system-reminder>The file is shorter than the requested offset.</system-reminder>

SztuCode currently reports these conditions through deterministic tool results
such as `[truncated]`; this reminder text must not invent a file event.
