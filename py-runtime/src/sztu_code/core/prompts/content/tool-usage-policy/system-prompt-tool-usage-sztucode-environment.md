# SztuCode tool environment

- File paths passed to built-in file tools must be relative to the working directory;
  do not use absolute paths.
- On Windows, the `bash` tool uses Git Bash rather than cmd. Use `ls`, `pwd`, `cat`,
  and `which`; forward slashes; `export VAR=val`; `$VAR`; `/dev/null`; and `cd path`.
  Do not use cmd-only forms such as `dir`, `where`, `set VAR=val`, `%VAR%`, `nul`,
  or `cd /d X`.
- Do NOT install packages or modify the environment with pip, npm, apt, brew, conda,
  or ensurepip unless the task explicitly requires it. Assume dependencies are
  already available.
- Prefer `edit_file` for targeted changes; `write_file` rewrites the whole file.
- When a tool fails, read the error, adjust the parameters, and retry. Do not repeat
  the exact same failing call.
