Analyze this CodeBuddy Code usage data and describe the user's interaction style.
{%- if language %}

IMPORTANT: Write ALL content in {{ language }}. The entire response must be in {{ language }}.
{%- endif %}

RESPOND WITH ONLY A VALID JSON OBJECT:
{
  "narrative": "2-3 paragraphs analyzing HOW the user interacts with CodeBuddy Code. Use second person 'you'. Describe patterns: iterate quickly vs detailed upfront specs? Interrupt often or let CodeBuddy Code run? Include specific examples. Use **bold** for key insights.",
  "key_pattern": "One sentence summary of most distinctive interaction style"
}

DATA:
{{ data }}
