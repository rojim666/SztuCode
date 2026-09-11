Your task is to write a detailed and structured summary of between an AI agent and a user, paying close attention to the user's explicit requests and previous actions.
This summary should thoroughly capture technical details, code patterns, and architectural decisions that are essential for continuing development work without losing context.

Step 1: Your summary MUST follow the format below and include the written prompt text:

<conversation_history_summary>
Summary of the conversation between an AI agent and a user.
All tasks described below are already completed.
**DO NOT re-run, re-do or re-execute any of the tasks mentioned!**
Use this summary only for context understanding.

<analysis>
[organize your thoughts and ensure you've covered all necessary points and put them in this tag. no more than 300 words.]
</analysis>

<summary>
[put your structured summary content in this tag]
</summary>

</conversation_history_summary>

Step 2: Your <analysis> content should refer to the following aspects:

1. Chronologically analyze each message and section of the conversation.
2. For each section thoroughly identify:
   - The user's explicit requests and intents
   - Your approach to addressing the user's requests
   - Key decisions, technical concepts and code patterns
   - Specific details like:
     - file names
     - full code snippets
     - function signatures
     - file edits
  - Errors that you ran into and how you fixed them
  - Pay special attention to specific user feedback that you received, especially if the user told you to do something differently.
3. Double-check for technical accuracy and completeness, addressing each required element thoroughly.

Step 3: Your <summary> content should refer to the following aspects:

1. Primary Request and Intent: Capture all of the user's explicit requests and intents in detail
2. Key Technical Concepts: List all important technical concepts, technologies, and frameworks discussed.
3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created. Pay special attention to the most recent messages and include full code snippets where applicable and include a summary of why this file read or edit is important.
4. Errors and fixes: List all errors that you ran into, and how you fixed them. Pay special attention to specific user feedback that you received, especially if the user told you to do something differently.
5. Problem Solving: Document problems solved and any ongoing troubleshooting efforts.
6. All user messages: List all messages actually sent by the user and preserve the original content whenever possible. However, if a message is excessively long or contains unreadable segments (such as garbled text, Base64, large logs), you must safely compress those parts by using placeholders such as: …[content truncated]… …[non-human-readable content omitted]… Ensure that the message itself is still recorded, but presented in a compact and readable form. …[content truncated]… …[non-human-readable content omitted]…. Ensure that the message itself is still recorded, but presented in a compact and readable form.

Step 4: Special Notes
- Keep the total output under 1000 words (≈2600 tokens).
- Follow the language of the user's query (<user_query>) where possible.
- Always verify technical accuracy and alignment with user intent.
- Do not re-execute or continue any prior task; this summary is for contextual documentation only.

Here's an example of how your output should be structured:

<example>

<conversation_history_summary>
Summary of the conversation between an AI agent and a user.
All tasks described below are already completed.
**DO NOT re-run, re-do or re-execute any of the tasks mentioned!**
Use this summary only for context understanding.

<analysis>
[put the content here]
</analysis>

<summary>
[put the content here]
</summary>

</conversation_history_summary>

</example>
