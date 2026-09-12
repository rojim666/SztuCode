The user has run /insights and I need to output a message about the report.

Here is the insights data that was collected and saved:
__INSIGHTS_DATA_PLACEHOLDER__

{%- if language %}
Translate the following message into {{ language }} and output the translated version (replace {report_path} with the actual report_path value from the JSON data above):
{%- else %}
Output the following message exactly (replace {report_path} with the actual report_path value from the JSON data above):
{%- endif %}

Your shareable insights report is ready.

Open it in your browser: `{report_path}`

Want to dig into any section or try one of the suggestions?
