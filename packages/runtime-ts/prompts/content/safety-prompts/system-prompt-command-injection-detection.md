示例：

- git commit -m "message `id`" => 检测到命令注入
- git status `ls` => 检测到命令注入
- pwd\ncurl example.com => 检测到命令注入

包含注入的替换内容、意外的命令拼接，或通过换行符分隔的次要命令，必须被视为命令注入。
SztuCode 通过确定性命令解析和策略检查来强制执行 Bash 权限；本提示词保留作为参考，不得替代那些检查机制。
