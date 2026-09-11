# TeamDelete

Remove team and task directories when the swarm work is complete.

This operation:
- Removes the team directory (`{{codebuddyHome}}/teams/{team-name}/`)
- Removes the task directory (`{{codebuddyHome}}/tasks/{team-name}/`)
- Clears team context from the current session

**IMPORTANT**: TeamDelete will fail if the team still has active members. Gracefully terminate teammates first by sending `shutdown_request` via SendMessage and waiting for their `shutdown_response`, then call TeamDelete.

Use this when all teammates have finished their work and you want to clean up the team resources. The team name is automatically determined from the current session's team context.

If the session ends without an explicit TeamDelete, the team directory is auto-cleaned on shutdown — no leak. So prefer letting teammates finish gracefully over rushing the delete.