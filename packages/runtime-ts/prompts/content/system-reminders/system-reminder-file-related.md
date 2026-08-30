<!--
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
-->
# 文件相关提醒

<system-reminder>警告：文件存在但为空。</system-reminder>

<system-reminder>
文件已被修改，可能是由用户或格式化程序修改的。在做出决策之前，请重新读取当前内容；不要假设之前的快照仍然有效。
</system-reminder>

<system-reminder>文件显示在第 N 行被截断。</system-reminder>

<system-reminder>文件短于请求的偏移量。</system-reminder>

SztuCode 当前通过确定性工具结果（例如 `[truncated]`）报告这些情况；此提醒文本不得虚构文件事件。
