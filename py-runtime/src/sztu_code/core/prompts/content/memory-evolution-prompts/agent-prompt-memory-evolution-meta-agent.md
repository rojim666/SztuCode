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


[memory-evolution] Analyze the failed task trajectory using specific evidence. For this invocation replace the report schema above with the SztuCode memory patch schema: return only a JSON array of at most 5 memory patches. Each patch needs target_note (kebab-case), proposed_content (at most 4096 bytes), attribution (note_content, state_representation or invocation_timing), evidence_refs (actual node_id values), and reason. Avoid duplicates, secrets and unsupported conclusions. Return [] when evidence is insufficient.
