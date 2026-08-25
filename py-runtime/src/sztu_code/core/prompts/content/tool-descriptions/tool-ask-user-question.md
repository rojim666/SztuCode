Ask the user one to three concise structured questions when a required decision or missing piece of information prevents correct progress. The tool waits for the user's response.

Usage:
- Use it to clarify ambiguous requirements, gather preferences, or obtain a consequential implementation decision.
- Each question requires a stable `id` and user-facing `question`; IDs must be unique.
- Optional choices may include up to eight items. Put a recommended option first and append `(Recommended)` to its label.
- Set `multi_select=true` only when more than one choice may be selected.
- Do not ask questions that can be answered safely by inspecting the workspace.
