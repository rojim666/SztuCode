Please analyze this codebase and create a CODEBUDDY.md file, which will be given to future instances of CodeBuddy Code to operate in this repository.
                    
What to add:
1. Commands that will be commonly used, such as how to build, lint, and run tests. Include the necessary commands to develop in this codebase, such as how to run a single test.
2. High-level code architecture and structure so that future instances can be productive more quickly. Focus on the "big picture" architecture that requires reading multiple files to understand

Usage notes:
- First check if there's already an AGENTS.md file in the current directory. If it exists, DO NOT create a new CODEBUDDY.md file. Instead, suggest improvements to the existing AGENTS.md file.
- If there's already a CODEBUDDY.md but no AGENTS.md, suggest improvements to the existing CODEBUDDY.md.
- If there's already a AGENTS.md but no CODEBUDDY.md, suggest improvements to the existing AGENTS.md.
- When creating a new file, create CODEBUDDY.md (not AGENTS.md) if neither exists.
- When you make the initial file, do not repeat yourself and do not include obvious instructions like "Provide helpful error messages to users", "Write unit tests for all new utilities", "Never include sensitive information (API keys, tokens) in code or commits".
- Don't include generic development practices
- If there are Claude Code rules (in ./CLAUDE.md) or Cursor rules (in .cursor/rules/ or .cursorrules) or Copilot rules (in .github/copilot-instructions.md) or ./AGENTS.md, make sure to include the important parts.
- If there is a README.md, make sure to include the important parts. 
- Do not make up information such as "Common Development Tasks", "Tips for Development", "Support and Documentation" unless this is expressly included in other files that you read.
- Be sure to prefix the file with the following text:

```
# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.
```

