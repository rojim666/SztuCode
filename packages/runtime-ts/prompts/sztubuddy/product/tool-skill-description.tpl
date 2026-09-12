Execute a skill within the main conversation

When users ask you to perform tasks, check if any of the available skills below match. Skills provide specialized capabilities and domain knowledge.

When users reference a "slash command" or "/<something>" (e.g., "/commit", "/review-pr"), they are referring to a skill. Use this tool to invoke it.

How to invoke:
- Use this tool with the skill name and optional arguments
- Examples:
  - `skill: "pdf"` - invoke the pdf skill
  - `skill: "commit", args: "-m 'Fix bug'"` - invoke with arguments
  - `skill: "ms-office-suite:pdf"` - invoke using fully qualified name

Important:
- When a skill matches the user's request, this is a BLOCKING REQUIREMENT: invoke the relevant Skill tool BEFORE generating any other response about the task
- NEVER mention a skill without actually calling this tool
- Do not invoke a skill that is already running
- Do not use this tool for built-in CLI commands (like /help, /clear, etc.)
- If you see a <command-name> tag in the current conversation turn, the skill has ALREADY been loaded - follow the instructions directly instead of calling this tool again
- If the name matches a deferred tool listed in <available_deferred_tools> (e.g., "Workflow"), do NOT use this Skill tool — use ToolSearch + DeferExecuteTool instead

<available_skills>
{%- if skills and skills.length > 0 -%}
{%- for skill in skills %}
- {{skill.name}}: {% if skill.truncatedDescription == undefined %}{{skill.description}}{% elif skill.truncatedDescription %}{{skill.truncatedDescription}}{% endif %} (location: {{skill.location}})
{%- endfor -%}
{%- endif %}
</available_skills>
{%- if skillsOverview and skillsOverview.truncationMode != 'none' %}
{%- if skillsOverview.omittedCount > 0 %}
<!-- Showing {{skillsOverview.shownCount}} of {{skillsOverview.totalCount}} skills due to token limits -->
{%- if skillsOverview.scanDirs and skillsOverview.scanDirs.length > 0 %}
More skills are available in these directories. Each subdirectory name is a skill name (containing a SKILL.md file). Discover them as needed, then invoke by name with this tool:
{%- for dir in skillsOverview.scanDirs %}
  - {{dir.path}}
{%- endfor %}
{%- endif %}
{%- else %}
<!-- Descriptions for some skills have been trimmed to fit token limits. All listed names remain callable. -->
{%- endif %}
{%- endif %}
