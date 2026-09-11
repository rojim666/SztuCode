Manage the lifecycle of user-created skills. This is a read-only guidance tool that returns paths, templates, and workflow instructions.

Supported actions:
- **list**: Returns all available skills with their descriptions, sources, and locations. Agent_created skills are marked with [agent_created].
- **create**: Returns the target directory path, a SKILL.md template with `agent_created: true` frontmatter, and step-by-step workflow instructions for creating the skill files and updating the registry.
- **modify**: After validating that the skill is agent_created (dual check: registry file + frontmatter), returns the skill directory structure and editing workflow.
- **delete**: After validating that the skill is agent_created, returns deletion workflow instructions (requires user confirmation).

Important:
- Only skills with `agent_created: true` in their SKILL.md frontmatter AND/OR registered in `agent-created-skills.json` can be modified or deleted.
- This tool does NOT directly create, modify, or delete any files. Follow the returned workflow instructions and use Write/Edit/Bash tools to perform the actual file operations.
- When creating a skill, you MUST update both the SKILL.md file and the `agent-created-skills.json` registry file.
- When deleting a skill, you MUST remove both the skill directory and the registry entry, and always confirm with the user first.
