Analyze this single CodeBuddy Code session transcript and produce a JSON summary.
{%- if language %}

IMPORTANT: Write the "underlying_goal", "friction_detail", and "brief_summary" fields in {{ language }}. Other fields (like category names and enum values) should remain in English for data consistency.
{%- endif %}

Session transcript:
{{ data }}

Return ONLY a JSON object with these fields:
{
  "underlying_goal": "What the user was trying to accomplish in 1-2 sentences",
  "goal_categories": { "category_name": count },
  "outcome": "fully_achieved | mostly_achieved | partially_achieved | not_achieved",
  "user_satisfaction_counts": { "satisfied": n, "likely_satisfied": n, "frustrated": n },
  "codebuddy_helpfulness": "essential | moderately_helpful | unhelpful",
  "session_type": "single_task | multi_task | quick_question | exploration",
  "friction_counts": { "type": count },
  "friction_detail": "Brief description of what went wrong, if anything",
  "primary_success": "What CodeBuddy did best in this session (e.g. fast_accurate_search, good_explanations, clean_code, none)",
  "brief_summary": "1-2 sentence summary of the session",
  "session_id": "{{ sessionId }}"
}

Goal categories to use: code_development, code_review, explore_codebase, information_request, tool_inquiry, game_development, documentation, debugging, refactoring, testing, configuration, create_session, warmup_minimal, other.

Friction types to use: misunderstood_request, user_rejected_action, buggy_code, wrong_approach, too_slow, missing_tool, other.

Be concise and accurate. Base your analysis only on the transcript provided.