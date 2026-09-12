Analyze this CodeBuddy Code usage data and identify project areas.
{%- if language %}

IMPORTANT: Write ALL content in {{ language }}. The entire response must be in {{ language }}.
{%- endif %}

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "areas": [
    {"name": "Area name", "session_count": N, "description": "2-3 sentences about what was worked on and how CodeBuddy Code was used."}
  ]
}

Include 4-5 areas. Skip internal CC operations.

DATA:
{{ data }}
