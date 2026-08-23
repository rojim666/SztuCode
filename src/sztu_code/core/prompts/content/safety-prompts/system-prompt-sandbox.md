# Sandbox reference

The referenced macOS sandbox profile denies access by default. It allows only
the required shell executables such as `/bin/bash` and `/usr/bin/env`, permits
file reads and `sysctl` reads, and denies file writes and network access.

This is a platform-specific reference. It does not claim that a sandbox is active
on unsupported platforms, and it must not be used as a substitute for runtime
process isolation or permission enforcement.
