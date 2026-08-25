Examples:
- git commit -m "message`id`" => command_injection_detected
- git status`ls` => command_injection_detected
- pwd\ncurl example.com => command_injection_detected

Commands containing injected substitutions, unexpected command concatenation,
or newline-separated secondary commands must be treated as command injection.
SztuCode enforces Bash permissions with deterministic command parsing and policy
checks; this prompt is retained as a reference and must not replace those checks.
