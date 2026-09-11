# Prompt Studio

SztuCode 系统提示词的规范化编排台：浏览、编辑并**用运行时真实函数**预览 TypeScript 链的提示词组装结果。

它不重新实现任何组装规则——编排预览通过子进程调用 `packages/runtime-ts/dist` 里的真实接口
（`buildSystemPrompt`、`buildDynamicContext`、`runtimePromptEntries`、`dynamicRuntimePromptEntries`、
`buildWorkbuddyBase`），因此所见即 daemon 实际下发的内容。

## 启动

```bash
npm run prompt-studio
# 打开 http://127.0.0.1:7440
```

环境变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PROMPT_STUDIO_PORT` | `7440` | 监听端口 |
| `PROMPT_STUDIO_HOST` | `127.0.0.1` | 绑定地址 |
| `PROMPT_STUDIO_NODE` | 自动探测 | 指定用于子进程的 node 可执行文件 |

> 首次使用前，若尚未构建过 TS 运行时，请先执行 `npm run build`（预览依赖 `packages/runtime-ts/dist`）。

## 界面

- **左：提示词库** — `prompts/content/*` 的 13 个分组（读取各组 `index.json`，标注 `active` / `reference-only`），
  以及 `prompts/workbuddy/` 的 main / styles / modes / contract 资源。支持即时过滤与空状态提示。
- **中：编辑器** — 打开条目后直接修改，实时显示字符/行/词数；有未保存修改时给出提示，切换条目会二次确认。
- **右：编排预览** — 配置 role / permission mode / interaction mode / 记忆开关 / 已注册工具（胶囊开关），
  实时得到分层的静态基座、运行时原子片段、完整 System Prompt 与动态 `<system-reminder>`，
  给出字符数与 token 估算、静动态占比条，每个区块可折叠并可一键复制。

### 键盘与无障碍

- `Ctrl/⌘ + S` 保存，`/` 聚焦搜索，`Esc` 清空搜索或取消聚焦。
- 折叠区块使用 `aria-expanded` 语义按钮，键盘可达；配色满足 WCAG AA 对比度。
- 尊重 `prefers-reduced-motion`；Lighthouse 无障碍 / 最佳实践 / SEO 均为 100。

## 映射到的实际接口

| UI / API | 运行时来源 |
| --- | --- |
| `POST /api/compose` 的静态基座 | `workbuddy-resources.buildWorkbuddyBase()` |
| 运行时原子片段 | `prompt-harness.runtimePromptEntries()`（工具→`tool-usage-policy` 映射表 + 恒注入 `executing-actions-with-care`） |
| 动态补充片段 | `prompt-harness.dynamicRuntimePromptEntries()`（mode / auto-mode / auto-memory） |
| System Prompt | `prompt-loader.buildSystemPrompt()` |
| 动态 reminder | `prompt-loader.buildDynamicContext()`（cwd/date、项目指令、skills、git、快照） |
| 提示词库 | `prompts/content/*/index.json` 与 `prompts/workbuddy/manifest.json` 所描述的资源树 |

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/state` | 目录树：分组、条目、workbuddy 资源 |
| `GET` | `/api/content?group=&file=` | 读取某个 content 条目（返回 `content`/`chars`/`sha256`） |
| `GET` | `/api/workbuddy?path=` | 读取某个 workbuddy 资源 |
| `PUT` | `/api/content` | 写回 `{ group, file, content, expectedSha256? }` |
| `PUT` | `/api/workbuddy` | 写回 `{ path, content, expectedSha256? }` |
| `POST` | `/api/compose` | 真实函数编排，返回分层结果与 metrics |

## 修改安全

- **路径边界**：拒绝绝对路径、`..` 遍历与 symlink 逃逸；仅允许编辑提示词包内的 `.md` / `.tpl`。
- **不新建文件**：只能编辑已存在的条目，避免在提示词目录里凭空产生文件。
- **备份**：每次写回前把旧内容存到 `.sztu/prompt-studio-backups/<时间戳>/<相对路径>`。
- **并发保护**：PUT 可带 `expectedSha256`，若磁盘已被其他进程改动则返回 `409`，不覆盖。
- **原子写**：先写临时文件再 `rename`。

## 生效范围

- 编辑写回的是 TS 运行时真正加载的提示词文件（`packages/runtime-ts/prompts/`）。
- TS daemon 对模板与索引有**进程级缓存**，修改后需**重启 daemon**（`npm run daemon:ts`）才会加载新内容；
  本工具自身的预览因为每次起新子进程，保存后即时反映。
- 桌面端为打包产物，需重新构建 / 打包后才会带上改动。
