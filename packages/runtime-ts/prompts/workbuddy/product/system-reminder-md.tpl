<system-reminder>
As you answer the user's questions, you can use the following context:
# codebuddyMd
Codebase and user instructions are shown below. Be sure to adhere to these instructions. IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.
{%- if userMemory.length > 0 or projectMemory.length > 0 or localMemory.length > 0 %}
<rules>
The rules section has a number of possible rules/memories/context that you should consider. In each subsection, we provide instructions about what information the subsection contains and how you should consider/follow the contents of the subsection.
<always_applied_workspace_rules description="These are rules set by the project that you should follow if appropriate.">
{%- for item in userMemory %}

Contents of {{item.filePath}} (user's private global instructions for all projects):

{{item.content}}
{%- endfor %}
{%- for memoryItem in projectMemory %}

Contents of {{memoryItem.filePath}} (project instructions, checked into the codebase):

{{memoryItem.content}}
{%- endfor %}
{%- for item in localMemory %}

Contents of {{item.filePath}} (user's private project instructions, not checked in):

{{item.content}}
{%- endfor %}
</always_applied_workspace_rules>
</rules>
{%- endif %}
      IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.
</system-reminder>
