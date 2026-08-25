Retrieve the status or final result of a background sub-agent started with `spawn_agent(run_in_background=true)`.

Usage:
- Pass the exact `run_id` returned by `spawn_agent`.
- The tool returns `still running` while the child is active, the final text when complete, or an error if the run is unknown, cancelled, or failed.
- Do not use this for foreground sub-agents because their result is returned directly by `spawn_agent`.
