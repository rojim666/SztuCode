#!/usr/bin/env node
import { spawn } from "node:child_process";
const query = `query($owner: String!, $repo: String!, $number: Int!, $commentsCursor: String, $reviewsCursor: String, $threadsCursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number url title state
      comments(first: 100, after: $commentsCursor) { pageInfo { hasNextPage endCursor } nodes { id body createdAt updatedAt author { login } } }
      reviews(first: 100, after: $reviewsCursor) { pageInfo { hasNextPage endCursor } nodes { id state body submittedAt author { login } } }
      reviewThreads(first: 100, after: $threadsCursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id isResolved isOutdated path line diffSide startLine startDiffSide originalLine originalStartLine resolvedBy { login } comments(first: 100) { nodes { id body createdAt updatedAt author { login } } } }
      }
    }
  }
}`;

type Page<T> = { pageInfo: { hasNextPage: boolean; endCursor: string | null }; nodes: T[] | null };
type PullRequest = { number: number; url: string; title: string; state: string; comments: Page<Record<string, unknown>>; reviews: Page<Record<string, unknown>>; reviewThreads: Page<Record<string, unknown>> };

async function gh(args: string[], input?: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn("gh", args, { stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8"); child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => { stdout += chunk; if (stdout.length > 16 * 1024 * 1024) child.kill(); });
    child.stderr.on("data", (chunk: string) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => code === 0 ? resolve(stdout) : reject(new Error(stderr.trim() || `gh exited with code ${code ?? "unknown"}`)));
    child.stdin.end(input);
  });
}

async function json<T>(args: string[], input?: string): Promise<T> { return JSON.parse(await gh(args, input)) as T; }

async function main(): Promise<void> {
  await gh(["auth", "status"]);
  const current = await json<{ number: number; headRepositoryOwner: { login: string }; headRepository: { name: string } }>(["pr", "view", "--json", "number,headRepositoryOwner,headRepository"]);
  const owner = current.headRepositoryOwner.login;
  const repo = current.headRepository.name;
  const comments: Record<string, unknown>[] = [];
  const reviews: Record<string, unknown>[] = [];
  const reviewThreads: Record<string, unknown>[] = [];
  let commentsCursor: string | null = null;
  let reviewsCursor: string | null = null;
  let threadsCursor: string | null = null;
  let metadata: Record<string, unknown> | null = null;

  do {
    const variables = ["-F", "query=@-", "-F", `owner=${owner}`, "-F", `repo=${repo}`, "-F", `number=${current.number}`];
    if (commentsCursor) variables.push("-F", `commentsCursor=${commentsCursor}`);
    if (reviewsCursor) variables.push("-F", `reviewsCursor=${reviewsCursor}`);
    if (threadsCursor) variables.push("-F", `threadsCursor=${threadsCursor}`);
    const payload = await json<{ data?: { repository?: { pullRequest?: PullRequest } }; errors?: unknown[] }>(["api", "graphql", ...variables], query);
    if (payload.errors?.length) throw new Error(`GitHub GraphQL errors: ${JSON.stringify(payload.errors)}`);
    const pr = payload.data?.repository?.pullRequest;
    if (!pr) throw new Error("GitHub response did not contain a pull request");
    metadata ??= { number: pr.number, url: pr.url, title: pr.title, state: pr.state, owner, repo };
    comments.push(...(pr.comments.nodes ?? [])); reviews.push(...(pr.reviews.nodes ?? [])); reviewThreads.push(...(pr.reviewThreads.nodes ?? []));
    commentsCursor = pr.comments.pageInfo.hasNextPage ? pr.comments.pageInfo.endCursor : null;
    reviewsCursor = pr.reviews.pageInfo.hasNextPage ? pr.reviews.pageInfo.endCursor : null;
    threadsCursor = pr.reviewThreads.pageInfo.hasNextPage ? pr.reviewThreads.pageInfo.endCursor : null;
  } while (commentsCursor || reviewsCursor || threadsCursor);

  console.log(JSON.stringify({ pull_request: metadata, conversation_comments: comments, reviews, review_threads: reviewThreads }, null, 2));
}

main().catch((error) => { console.error(error instanceof Error ? error.message : String(error)); process.exitCode = 1; });
