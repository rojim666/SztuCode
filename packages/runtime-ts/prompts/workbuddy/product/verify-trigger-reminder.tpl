<system-reminder data-role="verify-trigger">
The user invoked `/verify`{{target}} to validate recent code changes.

Verify that the recent code changes work as expected.

## Steps

1. **Identify changes**: Run `git diff` (or `git diff HEAD` if there are staged changes) to understand what was modified.

2. **Determine verification strategy**: Based on the type of changes:
   - If there are test files: run the relevant test suite
   - If there are build configuration changes: run the build
   - If there are API changes: test the endpoints
   - If there are UI changes: describe what to look for visually

3. **Run verification**:
   - Execute relevant test commands (e.g., `npm test`, `yarn test`, `pytest`, etc.)
   - Build the project if needed
   - Check for type errors, lint issues

4. **Report results**:
   - List what was tested and the outcome
   - Flag any failures or warnings
   - Confirm whether the changes work as intended or identify what needs fixing
</system-reminder>
