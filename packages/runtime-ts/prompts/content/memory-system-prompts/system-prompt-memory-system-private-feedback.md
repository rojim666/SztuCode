Analyze this SztuCode usage data and identify friction points for this user. Use second person ("you").
{%- if language %}

IMPORTANT: write_file ALL content in {{ language }}. The entire response must be in {{ language }}.
{%- endif %}

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "intro": "1 sentence summarizing friction patterns",
  "categories": [
    {"category": "Concrete category name", "description": "1-2 sentences explaining this category and what could be done differently. Use 'you' not 'the user'.", "examples": ["Specific example with consequence", "Another example"]}
  ]
}

Include 3 friction categories with 2 examples each.

DATA:
{{ data }}
