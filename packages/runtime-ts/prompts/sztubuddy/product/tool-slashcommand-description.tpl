Execute a slash command within the main conversation

This tool supports both **custom slash commands** and **built-in commands**. Use it to execute slash commands on behalf of the user.

Usage:
- `command` (required): The slash command to execute, including any arguments
- Example: `command: "/model list"`, `command: "/model gpt-4o"`, `command: "/config list"`, `command: "/context"`

## Built-in Commands

You can call these built-in commands when the user's intent matches. All built-in commands support a parameter mode for model-driven calls. Without parameters they open an interactive panel (TUI only).

**Information queries (no approval needed):**
- `/help` - Show help and available commands
- `/status` - Show version, model, account, API connectivity, and tool statuses
- `/todos` - Display the current session's todo list
- `/plan` - Preview the current plan file content
- `/skills` - List available skills
- `/tasks` - List and manage background tasks
- `/model list` - List all available models with current selection
- `/resume list` - List all available sessions (id, time, summary)
- `/resume <session-id>` - Resume a specific session
- `/config list` - List current settings
- `/config get <key>` - Get a specific setting value

**Configuration changes (needs approval):**
- `/model <model-id>` - Switch the AI model (e.g., `/model gpt-4o`)
- `/model:text-to-image list` - List available text-to-image models
- `/model:text-to-image <model-id>` - Switch the text-to-image model
- `/model:image-to-image list` - List available image-to-image models
- `/model:image-to-image <model-id>` - Switch the image-to-image model
- `/config set <key> <value>` - Change a setting (e.g., `/config set theme dark`)
- `/clear` - Start a fresh conversation
- `/rename <name>` - Rename the current conversation
- `/theme` - Configure theme
- `/output-style` - Set the output style

Do NOT use this tool for commands not listed above (e.g., /exit, /login, /vim, etc.).
{%- if truncatedCustomCommands.length > 0 %}

## Custom Commands
{%- for command in truncatedCustomCommands %}
- {{command.name}} {{command.argumentHint}}: {{command.description}}
{%- endfor %}
{%- if truncatedCustomCommands.length < customCommands.length %}

(Showing {{truncatedCustomCommands.length}} of {{customCommands.length}} commands due to token limits)
{%- endif %}
{%- endif %}

Notes:
- When a user requests multiple slash commands, execute each one sequentially and check for <command-message>{name} is running…</command-message> to verify each has been processed
- Do not invoke a command that is already running. For example, if you see <command-message>foo is running…</command-message>, do NOT use this tool with "/foo" - process the expanded prompt in the following message
