<system-reminder>{% if todoListEmpty %}
This is a reminder that your task list is currently empty. DO NOT mention this to the user explicitly because they are already aware. If you are working on tasks that would benefit from a task list please use the task_create tool to create tasks. If not, please feel free to ignore. Again do not mention this message to the user.
{% else %}
Your task list has changed. DO NOT mention this explicitly to the user. Here are the latest contents of your task list:

{{todoListContent | safe}}. Continue on with the tasks at hand if applicable.
{% endif %}
</system-reminder>
