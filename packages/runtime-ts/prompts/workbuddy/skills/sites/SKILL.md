---
name: 发布为应用
description: 将生成内容发布为在线链接，或取消发布已上线的应用。适合网站、小游戏等交互式内容，支持任意可作为单端口 HTTP 服务运行的项目（静态站点 / PDF / Node.js / Python / Go）。当用户想把本地项目部署、发布、上线、生成分享链接、在云端预览或下线分享链接时使用。
license: Internal
allowed-tools:
disable: false
---

# 发布应用 / Sites

Publish a local project as an online link via the built-in `Sztubuddy_sites_deploy` tool.
Unlike static-only deploy, this supports any project that can run as a single-port HTTP
service: static sites, PDFs, small games, and backend HTTP apps (Node.js / Python / Go).

## When to Use

- User asks to **deploy / publish / go live / share an online link / preview in the cloud**.
- User @-mentions **sites** / 发布应用.
- User has a project (static output or a runnable HTTP app) and wants a live, shareable URL.

## Ask Before Deploying — Consent Does Not Carry Over

Deploying is a release to the outside world: it overwrites whatever is currently live behind a
link the user may already have shared with other people. Every deploy therefore needs consent
**for that turn**.

Count the user as having asked to publish only when their **latest message** does one of these:

- uses a publish verb — 发布 / 上线 / 部署 / 同步到线上 / 更新线上 / publish / deploy / go live /
  redeploy / "put it online";
- @-mentions **sites** / 发布应用;
- asks for a shareable online link.

Everything else means they have **not** asked, and you ASK first (in their language) before
calling the tool. In particular, agreeing to publish earlier in this conversation does **not**
authorize the next deploy. Do NOT silently deploy.

## Changing an App That Is Already Published

This is the common follow-up: the app is live, and the user now says 「把标题改成 X」/「按钮再大一点」/
「修一下这个 bug」. What they asked for is a **local change**, not a release. Publishing anyway
replaces the page other people may be looking at right now, and the user never got a say in it.

After you finish the edit:

1. Say what you changed and let the user check it in the local preview.
2. Ask exactly one question, in their language — e.g. 「改动已经完成，需要我把它同步更新到线上分享
   链接吗？（线上现有内容会被覆盖）」
3. **End your turn and wait.** Deploy only after an explicit yes.

If the user declines, leave the live link untouched and tell them the changes stay local.

The tool enforces this as well: deploying into a directory that still has a live link without
`userAskedToPublish: true` comes back as `{"type":"sites_deploy_needs_confirmation"}` and nothing is
published. Relay its `userMessage` and wait for the answer. Do **not** re-call the tool with the
flag flipped on just to get past the check — that flag records what the user asked for, it is not a
retry switch.

## Unpublish (take offline)

To unpublish / take a published site offline / cancel a publish, use the built-in
`Sztubuddy_sites_deploy` tool with `action: "unpublish"` and the same project `directory`
that was deployed. After unpublishing, the shared link stops working. This is destructive —
if the user was not explicit, confirm first. If the directory was never published or is
already offline, tell the user that instead of pretending it was taken offline.

## What Can Be Published

Only projects reachable as a **single public port** HTTP service (via a reverse-proxied
domain) can be published:

- **Static site / PDF / assets** — served automatically with an internal HTTP server; no
  build required beyond producing the files.
- **Runnable HTTP app** (Express / FastAPI / Go http, etc.) — source is uploaded,
  dependencies are installed in a sandbox, and the server is started on one port.

The sandbox gives the app **one HTTP port and nothing else** — no database, cache or message
queue runs alongside it. So when an app needs to persist data and you are the one writing it,
keep the storage inside the app: **SQLite**, a JSON file, or browser-side storage all publish
fine. Reaching for MySQL / PostgreSQL / Redis / MongoDB makes the project unpublishable here.

If the project genuinely CANNOT be exposed as an HTTP service, tell the user the current
directory does not support publishing — do NOT force a deploy. See **Unsupported Projects &
No Silent Downgrade** below for the exact types that are rejected and how to respond.

## Unsupported Projects & No Silent Downgrade

The publishing sandbox natively supports **Node.js / Python / Go / static sites** as a single
public HTTP port. It does **NOT** support:

- **Mini programs** (WeChat / Alipay / ByteDance / Baidu). Publishing produces a web page
  behind one HTTP port; a mini program must be built, packaged, signed and released through
  its vendor open platform. A directory is rejected when it — **or any of its immediate
  subdirectories** — carries `project.config.json` / `app.wxss` / `app.acss` / `app.ttss`, or an
  `app.json` with a `pages` array. Just say publishing a mini program is not supported and hand
  it back to its own toolchain: open the project in **WeChat DevTools**, fill in a real AppID
  registered on **微信公众平台**, then 上传 → 提交审核 → 发布.
  **NEVER convert a mini program into a web page to get something published.** Writing an
  HTML/H5 version of the mini program and deploying that — or deploying a sibling `index.html`
  next to the mini-program directory — is strictly forbidden, even though it makes the publish
  "succeed". The user asked for a mini program; a web link is not one, and handing them one
  reads as if the request was fulfilled. Deploy nothing for such a request. If the user
  afterwards explicitly asks for a web version as well, that is a new request they have to make.
- **Java / Maven / Gradle** projects (no JVM/Maven/Gradle build in the sandbox).
- Projects that need **external services** the sandbox does not provide — MySQL, PostgreSQL,
  Redis, MongoDB, Kafka, RabbitMQ. Only a single HTTP port is exposed; there is no database,
  cache or message queue alongside it. A directory is rejected when it declares one through a
  connection string in `.env*` pointing at localhost or a compose service name, a
  `prisma/schema.prisma` provider other than `sqlite`, external service containers in
  `docker-compose.yml`, a Spring datasource, or a driver package in its dependency manifest
  (`mysql2` / `pg` / `mongoose` / `ioredis` / `psycopg2` / `go-sql-driver/mysql`, …).
  **SQLite is fully supported** — it ships with the project and runs inside the sandbox — and a
  connection string pointing at a public managed database (e.g. Supabase) is allowed too,
  because the sandbox can reach the internet.

The `Sztubuddy_sites_deploy` tool runs this **pre-check before uploading anything**. An
unsupported project comes back as `{"type":"sites_deploy_unsupported"}` carrying a
ready-to-use `userMessage` (plus an internal `agentGuidance`). When that happens:

- **Relay `userMessage` to the user** — translated into the reply language, keeping every point
  it makes — and then **STOP**. Do not invent a different explanation, and do not read
  `agentGuidance` out to them; that field is instructions for you.
- **NEVER silently fall back to a static placeholder / "project overview" page.** This was the
  #1 complaint: the Skill quietly downgraded a Go/Java project to a static page and the user
  had to cancel. If a static-page downgrade might genuinely help, **ASK the user first** with a
  clear yes/no question (e.g. "Deploying this project directly isn't supported. Do you want me
  to publish a static page showing its structure/docs instead?") and only proceed on explicit
  approval.
- **Never retry to force it through** — not with a different `language`, `installCmd` or
  `startCmd`, and not by stripping the project's database on your own. Switching the storage to
  SQLite or browser-side storage does make such a project publishable, so it is a good thing to
  *propose*, but rewriting someone's project unasked is not.
- If dependency install fails **during** deploy (e.g. a Go project whose modules can't be
  downloaded), report the failure and the likely cause — **do not** switch strategies on your
  own. Suggest concrete fixes (e.g. run `go mod vendor` so deps ship with the source) or ask
  the user how to proceed.
- A project that slips past the pre-check and then fails to start because it cannot reach a
  database is reported the same way (`sites_deploy_unsupported` with a `userMessage`) instead of
  as a raw startup timeout. Relay it and stop; the same no-downgrade, no-retry rules apply.

## Requirements the Project Must Meet

- The service MUST listen on the `PORT` environment variable and bind `0.0.0.0`.
- Pure static / PDF: no hand-rolled fragile server needed — the tool serves it with an
  internal HTTP server (or `python3 -m http.server "$PORT" --bind 0.0.0.0`).
- Vite-based frameworks (Vite / Vue / React / Svelte): the dev/preview server MUST allow the
  reverse-proxy host — set `server.host = "0.0.0.0"` and add the deploy domain to
  `server.allowedHosts` (or `allowedHosts: true`, or `--host 0.0.0.0`), otherwise
  Vite rejects the request with "Blocked request. This host is not allowed."

## How to Deploy

Use the built-in tool `Sztubuddy_sites_deploy`. It accepts:

- `action` (optional) — `deploy` (default) / `unpublish`.
- `directory` (required) — absolute path to the local project source directory.
- `language` (deploy only) — `node` / `python` / `go` / `static` / `auto` (default `auto`).
- `port` (deploy only) — the single public port (injected as `PORT`), auto-detected or 3000.
- `installCmd` (deploy only) — override the auto-detected install command; empty string skips.
- `startCmd` (deploy only) — override the auto-detected start command; must listen on `$PORT`.
- `appName` (deploy only) — a short human-friendly display name for the app list, which YOU
  summarize from what the app actually is (e.g. 「A股行业轮动监控看板」, 「快速排序可视化」). Keep it
  under ~12 characters, in the user's language. Not the directory name, not the conversation
  title. Always provide it; it falls back to the directory name when omitted.
- `userAskedToPublish` (deploy only) — set to `true` **only** when the user asked to publish in
  their **latest** message. See **Step 0** below.
- `miniProgramRequested` (deploy only) — set to `true` **only** when the user asked for a mini
  program somewhere in this conversation. See **Report result** below.

## Workflow

Be **conservative** — only proceed with build/deploy when you have high confidence.

### Step 0: Do you have consent for THIS turn?

Before anything else, check the user's latest message against **Ask Before Deploying** above.

- Asked to publish → pass `userAskedToPublish: true` and continue.
- Did not ask → finish the local work, then ask whether to publish and **stop there**. Continue
  from Step 1 only after they say yes.

This is a gate, not a formality. A conversation that already published once still has to pass it
again before the next deploy.

### Step 1: Identify the deploy target

If the user specified a directory, verify it looks deployable. Otherwise infer the project
root or the relevant build/source directory from the conversation.

### Step 1.5: Ensure files are written to disk FIRST

Only deploy AFTER every project file has been fully written to the target directory on disk.
The tool compresses and uploads the directory as-is — if you deploy before the code is saved
(or while files are still being written), an empty/partial directory gets uploaded and the
site will be empty/broken. Finish writing all files and confirm they exist under the
directory before calling the tool.

### Step 2: Empty directory → develop first

If the target directory is empty (nothing built yet), the tool returns dev guidance. Do NOT
deploy — develop the project first as a single-port HTTP service, then deploy again.

### Step 3: Deploy

Call `Sztubuddy_sites_deploy` with the identified directory (plus optional overrides):

```json
{ "directory": "/absolute/path/to/project", "userAskedToPublish": true }
```

The tool probes the project, uploads the source (compressed, excluding `node_modules`/`.git`/
build output), installs dependencies inside the sandbox, starts the server on one port, and
returns the access URL.

Re-publishing the same directory reuses the existing sandbox, so the share link stays the same —
which also means the content behind that link is **replaced**, irreversibly, for everyone who
already has it. Convenient to do, not automatic to decide: it still needs Step 0 consent.

### Step 4: Report result

A successful deploy returns JSON with `shareLink`, `verified`, `deployedAs` and `manageGuidance`.

- Present the `shareLink` as the **分享链接** to the user.
- Follow `manageGuidance`: right after the link, tell the user in bold where to manage the app they just
  published — 中文用「设置—数据管理—我发布的应用」，English uses "Settings - Data Management - Published Apps".
  Say it on every successful deploy, re-publishes included.
- Do NOT mention expiration, spaceKey, data plane URL, webIDE URL, or other internal details.
- If `verified` is `false`, suggest waiting a few seconds and retrying the link.

### The mini program notice is conditional — do not volunteer it

What this skill publishes is always a web page / HTTP service at a URL (`deployedAs` is
`web-page` for a pure HTML artifact), never a mini program. That fact only needs saying when the
user expected a mini program:

- **If the user mentioned 小程序 / 微信小程序 / mini program / miniprogram anywhere in this
  conversation**, pass `miniProgramRequested: true`. The result then carries a
  `miniProgramNotice` that you MUST relay alongside the link — translated into their language,
  keeping every point it makes. It already contains the accurate wording (the only path is
  **代码开发 (Coding) → 小程序 (Mini Program)**; the current HTML cannot be converted or
  reorganized into a mini program; WeChat DevTools cannot help because it only opens an existing
  mini-program project), so do NOT rewrite the explanation yourself. This matters most when the
  artifact was just an `index.html`: without it the user is left thinking the publish failed, or
  that the link somehow *is* the mini program. Never state or imply that a mini program was
  published.
- **Keep passing the flag and keep relaying the notice on re-publishes and content updates** in
  that same conversation. Do NOT drop it because you already said it in an earlier turn — a user
  who republishes still needs to know the new link is a web page, and skipping it the second time
  reads as if the situation changed.
- **If the user never mentioned a mini program, leave the flag out and do not raise the topic at
  all.** No notice, and no unsolicited remark that the link is "a web page, not a mini program".
  Someone who asked for a small game or a dashboard does not need to be told what they did not
  ask about; saying it anyway is noise.

## Important Rules

- Only show the `shareLink`, referred to as **分享链接**. Hide all internal details.
- Be conservative in build attempts — never fabricate or guess build commands. If the setup
  is complex (monorepo, unconventional build), stop and ask the user.
- The tool handles workspace creation, upload, dependency install, server start, and link
  generation internally.
