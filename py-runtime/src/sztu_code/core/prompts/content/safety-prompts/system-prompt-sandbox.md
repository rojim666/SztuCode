# 沙箱参考
<!--
# Sandbox reference
-->

<!--
The referenced macOS sandbox profile denies access by default. It allows only
the required shell executables such as `/bin/bash` and `/usr/bin/env`, permits
file reads and `sysctl` reads, and denies file writes and network access.

This is a platform-specific reference. It does not claim that a sandbox is active
on unsupported platforms, and it must not be used as a substitute for runtime
process isolation or permission enforcement.
-->
所引用的 macOS 沙箱配置文件默认拒绝访问。它仅允许必需的 shell 可执行文件，如 `/bin/bash` 和 `/usr/bin/env`，允许文件读取和 `sysctl` 读取，拒绝文件写入和网络访问。

这是一个特定于平台的参考。它不声称沙箱在不受支持的平台上处于活动状态，且不得将其用作运行时进程隔离或权限强制执行的替代方案。
