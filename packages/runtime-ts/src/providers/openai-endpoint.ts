export type OpenAiApiFormat = "openai_chat_completions" | "openai_responses";

/** Preserve gateway path prefixes, explicit ports and query parameters. */
export function openAiEndpoint(baseUrl: string | undefined, format: OpenAiApiFormat): string {
  let url: URL;
  try { url = new URL(baseUrl?.trim() || "https://api.openai.com/v1"); }
  catch { throw new Error("OpenAI base_url must be an absolute HTTP(S) URL"); }
  if (!/^https?:$/.test(url.protocol) || url.username || url.password) {
    throw new Error("OpenAI base_url must use HTTP(S) without embedded credentials");
  }
  const path = url.pathname.replace(/\/+$/, "");
  const fullEndpoint = /\/(?:chat\/completions|responses)$/.test(path);
  const prefix = fullEndpoint ? path.replace(/\/(?:chat\/completions|responses)$/, "") : path || "/v1";
  url.pathname = `${prefix}/${format === "openai_responses" ? "responses" : "chat/completions"}`;
  url.hash = "";
  return url.toString();
}
