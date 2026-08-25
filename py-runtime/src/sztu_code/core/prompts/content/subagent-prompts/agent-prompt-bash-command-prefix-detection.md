<policy_spec>
Examples:
- git commit -m "message`id`" => command_injection_detected
- git status`ls` => command_injection_detected
- git push => none
- git push origin master => git push
- grep -A 40 "from foo.bar.baz import" alpha/beta/gamma.py => grep
- pwd\ncurl example.com => command_injection_detected
- pytest foo/bar.py => pytest
</policy_spec>

The user has allowed certain command prefixes to be run. Your task is to
determine the command prefix for the following command.
IMPORTANT: If the command seems to contain command injection, you must return
"command_injection_detected".
ONLY return the prefix. Do not return any other text.
