Unpublish an artifact: make a previously published HTML page or Markdown document private so its public link stops working.

This is currently the ONLY action ArtifactControl supports (no list / delete / permission-edit yet).

Use this tool when the user wants to unpublish / take down / revoke / 取消分享 / 下线 / 设为私密 a link that was created with the Artifact tool — e.g. "unpublish that link", "取消这个分享", "make it private again", "I shared a sensitive file, take it down".

Parameters (provide at least one):
- shareLink: the full share link URL returned by Artifact (e.g. "https://workbuddy.link/p/abc123"). This is the easiest option — just pass back the link.
- nodeId: alternatively, the bare identifier (the segment after "/p/" in the share link).

Behavior:
- Revokes public access for the referenced page using your current session's credentials. After this succeeds, the link stops rendering publicly.
- For Markdown document links it also removes collaborators, making the doc fully private.
- Works for links created in this session or earlier sessions, since the identifier is derivable from the link URL — no session history is required.

If the user only has the link text, pass it as shareLink; you do not need to ask them for an internal id.
