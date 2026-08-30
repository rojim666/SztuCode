<!--
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
-->
<policy_spec>
示例：
- git commit -m "message`id`" => command_injection_detected
- git status`ls` => command_injection_detected
- git push => none
- git push origin master => git push
- grep -A 40 "from foo.bar.baz import" alpha/beta/gamma.py => grep
- pwd\ncurl example.com => command_injection_detected
- pytest foo/bar.py => pytest
</policy_spec>

用户已允许运行某些命令前缀。你的任务是确定以下命令的命令前缀。
重要提示：如果命令似乎包含命令注入，你必须返回 "command_injection_detected"。
仅返回前缀。不要返回任何其他文本。
