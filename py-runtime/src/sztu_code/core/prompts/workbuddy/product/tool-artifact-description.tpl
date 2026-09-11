Upload a local HTML or Markdown file and publish it as an artifact: a shareable public link that renders the page.

Use this tool when the user wants a shareable link (分享链接) or public URL for a single local document — e.g. "give me a shareable link", "publish this HTML", "把这个页面分享出去", "分享这份 Markdown".

Parameters:
- filePath (required): absolute path to the local file to publish. Supported extensions: `.html` / `.htm` and `.md` / `.markdown`.
- existingShareLink (optional): a share link previously returned by this tool (or its bare nodeId). When provided, the referenced page is updated in place and the SAME link is returned. Omit it to create a new link.

Behavior:
- Deploys the document using your current session's credentials and returns a public link that opens/renders the page in a browser.
- Markdown is rendered server-side as a styled page — do NOT pre-render it to HTML yourself, just pass the `.md` file.
- Only supports a single file. For multi-file sites or build directories, this tool is not applicable.
- Failures are reported explicitly: an oversized file and content that fails moderation each produce a distinct error rather than a generic one.
- Updating across sessions works as long as you pass the original link back via `existingShareLink`; without it a new page is always created.
- To make a published link private again later, use the ArtifactControl tool.

Present only the returned shareLink to the user; do not expose internal identifiers.
