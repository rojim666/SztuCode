# Claw-Code 工具系统架构文档

> 用于复刻参考。覆盖权限模式定义、权限判断逻辑、工具注册/执行/分发全链路。

---

## 一、权限系统

### 1.1 权限模式定义

**文件：** `rust/crates/runtime/src/permissions.rs:8-15`

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum PermissionMode {
    ReadOnly,          // "read-only"
    WorkspaceWrite,    // "workspace-write"
    DangerFullAccess,  // "danger-full-access"
    Prompt,            // "prompt"
    Allow,             // "allow"
}
```

`#[derive(PartialOrd, Ord)]` 关键：变体定义顺序即为权限层级，`ReadOnly < WorkspaceWrite < DangerFullAccess < Prompt < Allow`。

核心比较：`current_mode >= required_mode` → 允许。

### 1.2 用户可见的别名映射

**CLI 层** (`rusty-claude-cli/src/main.rs:11077`)：

| 用户输入 | 归一化到 |
|---|---|
| `default`, `plan`, `read-only` | `read-only` |
| `acceptEdits`, `auto`, `workspace-write` | `workspace-write` |
| `dontAsk`, `bypassPermissions`, `dangerFullAccess`, `danger-full-access` | `danger-full-access` |

**配置文件层** (`runtime/src/config.rs:2043`)：同上映射，另增 `prompt`、`allow` 两个无历史别名的新模式。

### 1.3 配置来源优先级

**文件：** `rusty-claude-cli/src/main.rs:3076-3099`

```
1. CLI flag:      --permission-mode <mode>
2. 环境变量:       RUSTY_CLAUDE_PERMISSION_MODE
3. 配置文件:       settings.json → permissions.defaultMode (新)
                   settings.json → permissionMode         (旧, deprecated)
4. 默认值:         WorkspaceWrite
```

### 1.4 授权判断流程

**核心函数：** `PermissionPolicy::authorize_with_context()` (`permissions.rs:186`)

```
authorize(tool_name, input)
  │
  ├─ 1. denied_tools 列表匹配 → 无条件 Deny
  ├─ 2. deny_rules 规则匹配   → Deny (如 "bash(rm -rf:*)")
  │
  ├─ 3. Hook 覆盖检查 (PermissionContext.override_decision):
  │     ├─ Deny  → 直接拒绝
  │     ├─ Ask   → 弹窗询问用户
  │     └─ Allow → 继续后续检查
  │
  ├─ 4. ask_rules 匹配 → 强制弹窗 (即使模式本该允许)
  ├─ 5. allow_rules 匹配 或 current_mode >= required_mode → Allow
  │
  ├─ 6. 当前 Prompt 模式 → 弹窗
  ├─ 7. WorkspaceWrite → DangerFullAccess 升级 → 弹窗
  │
  └─ 8. 其他 → Deny
```

### 1.5 权限规则语法

**文件：** `permissions.rs:369-467`

```
规则格式:  ToolName(matcher)
  - bash(git:*)    → 前缀匹配: bash 工具, command 字段以 "git" 开头
  - bash(rm -rf)   → 精确匹配: bash 工具, command 字段等于 "rm -rf"
  - bash(*)        → 匹配所有 bash 调用 (等效于 bash)
  - Bash           → 匹配所有 Bash 调用 (大小写不敏感)

matcher 从输入的 JSON 中提取 subject:
  优先取: command > path > file_path > filePath > url > pattern > code > message
```

---

## 二、工具定义层

### 2.1 ToolSpec 结构

**文件：** `rust/crates/tools/src/lib.rs:104-111`

```rust
pub struct ToolSpec {
    pub name: &'static str,                // 发送给模型的名字
    pub description: &'static str,         // system prompt 中的用途说明
    pub input_schema: Value,               // JSON Schema
    pub required_permission: PermissionMode, // 基准权限
}
```

### 2.2 内置工具一览

**文件：** `lib.rs:484` (`mvp_tool_specs()`)

#### ReadOnly 级工具

| 工具名 | 描述 | 关键参数 |
|---|---|---|
| `read_file` | 读取文本文件 | `path`, `offset?`, `limit?` |
| `glob_search` | Glob 模式搜索文件 | `pattern`, `path?` |
| `grep_search` | 正则搜索文件内容 | `pattern`, `path?`, `glob?`, `output_mode?`, `-A?`, `-B?`, `-C?`, `-i?`, `head_limit?`, `offset?`, `multiline?`, `type?` |
| `Skill` | 加载技能定义 | `skill`, `args?` |
| `ToolSearch` | 搜索延迟加载工具 | `query`, `max_results?` |
| `Sleep` | 等待指定时长 | `duration_ms` |
| `SendUserMessage` | 向用户发消息 | `message`, `attachments?`, `status` |
| `AskUserQuestion` | 向用户提问并等待回复 | `question`, `options?` |
| `StructuredOutput` | 返回结构化 JSON | 任意 key-value |
| `LSP` | LSP 语言服务 | `action`, `path?`, `line?`, `character?`, `query?` |

#### WorkspaceWrite 级工具

| 工具名 | 描述 | 关键参数 |
|---|---|---|
| `write_file` | 覆盖写文件 | `path`, `content` |
| `edit_file` | 字符串替换编辑 | `path`, `old_string`, `new_string`, `replace_all?` |
| `TodoWrite` | 持久化任务列表 | `todos[{content, activeForm, status}]` |
| `Config` | 读写设置 | `setting`, `value?` |
| `EnterPlanMode` | 进入计划模式 | (无参数) |
| `ExitPlanMode` | 退出计划模式 | (无参数) |
| `NotebookEdit` | 编辑 .ipynb | `notebook_path`, `cell_id?`, `new_source?`, `cell_type?`, `edit_mode?` |

#### DangerFullAccess 级工具

| 工具名 | 描述 | 关键参数 |
|---|---|---|
| `bash` | 执行 Shell 命令 | `command`, `timeout?`, `description?`, `run_in_background?`, `dangerouslyDisableSandbox?` |
| `PowerShell` | 执行 PowerShell | `command`, `timeout?`, `description?`, `run_in_background?` |
| `WebFetch` | 抓取网页 | `url`, `prompt` |
| `WebSearch` | 搜索网页 | `query`, `allowed_domains?`, `blocked_domains?` |
| `Agent` | 启动子 Agent | `description`, `prompt`, `subagent_type?`, `model?`, `name?` |
| `REPL` | 代码解释执行 | `code`, `language`, `timeout_ms?` |
| `TaskCreate` | 创建后台任务 | `prompt`, `description?` |
| `RunTaskPacket` | 结构化任务包 | `objective`, `scope`, `repo?`, `branch_policy?`, `acceptance_tests?`, `commit_policy?`, `reporting_contract?`, `escalation_policy?` |
| `TaskGet` | 获取任务 | `task_id` |
| `TaskList` | 列出任务 | (无参数) |
| `TaskStop` | 停止任务 | `task_id` |
| `TaskUpdate` | 更新任务 | `task_id`, `message` |
| `TaskOutput` | 获取任务输出 | `task_id` |

#### 其他工具

| 工具名 | 级别 | 描述 |
|---|---|---|
| `WorkerCreate` ~ `WorkerObserveCompletion` (8个) | DangerFullAccess | Worker 进程管理 |
| `TeamCreate` / `TeamDelete` | DangerFullAccess | 团队/多 agent 编排 |
| `CronCreate` / `CronDelete` / `CronList` | DangerFullAccess | 定时任务 |
| `GitStatus` / `GitDiff` / `GitLog` / `GitShow` / `GitBlame` | ReadOnly | Git 只读操作 |
| `MCP` | DangerFullAccess | MCP 工具调用 |
| `ListMcpResources` / `ReadMcpResource` | ReadOnly | MCP 资源读取 |
| `McpAuth` | DangerFullAccess | MCP 认证 |
| `RemoteTrigger` | DangerFullAccess | 远程触发 |
| `TestingPermission` | DangerFullAccess | 测试用权限验证 |

### 2.3 核心工具 vs 延迟工具

**文件：** `lib.rs:5550`

```rust
fn deferred_tool_specs() -> Vec<ToolSpec> {
    mvp_tool_specs().into_iter().filter(|spec| {
        !matches!(spec.name,
            "bash" | "read_file" | "write_file" | "edit_file"
            | "glob_search" | "grep_search"
        )
    }).collect()
}
```

这 6 个工具始终直接呈现给模型，其他的通过 `ToolSearch` 按需发现。

---

## 三、工具注册层

### 3.1 GlobalToolRegistry

**文件：** `lib.rs:112-434`

```rust
pub struct GlobalToolRegistry {
    plugin_tools: Vec<PluginTool>,        // 插件注入的工具
    runtime_tools: Vec<RuntimeToolDefinition>, // MCP 等运行时工具
    enforcer: Option<PermissionEnforcer>, // 权限门卫
}
```

**构建方法：**

```rust
GlobalToolRegistry::builtin()
    .with_plugin_tools(plugins)?     // 冲突检测: 不与内置重名
    .with_runtime_tools(mcp_tools)?  // 冲突检测: 不与内置+插件重名
    .with_enforcer(enforcer)         // 绑定权限
```

**关键方法：**

| 方法 | 说明 |
|---|---|
| `definitions(allowed_tools)` | 过滤后输出 `Vec<ToolDefinition>` → 发给模型 |
| `execute(name, input)` | 内置 → `execute_tool_with_enforcer`；插件 → 自有 execute |
| `search(query, max_results)` | 关键词打分排序搜索 |
| `normalize_allowed_tools(values)` | `--allowedTools` 白名单解析，支持别名和大小写不敏感 |
| `permission_specs(allowed_tools)` | 输出每个工具的权限要求 |

**工具名别名：**

```rust
"read"  → "read_file"     "Read"  → "read_file"
"write" → "write_file"    "Write" → "write_file"
"edit"  → "edit_file"     "Edit"  → "edit_file"
"glob"  → "glob_search"   "Glob"  → "glob_search"
"grep"  → "grep_search"   "Grep"  → "grep_search"
```

---

## 四、工具执行层

### 4.1 总入口：`execute_tool_with_enforcer`

**文件：** `lib.rs:1369-1500`

```rust
fn execute_tool_with_enforcer(
    enforcer: Option<&PermissionEnforcer>,
    name: &str,
    input: &Value,
) -> Result<String, String> {
    match name {
        "bash" => {
            let bash_input: BashCommandInput = from_value(input)?;
            let classified = classify_bash_permission(&bash_input.command);
            maybe_enforce_permission_check_with_mode(enforcer, name, input, classified)?;
            run_bash(bash_input)
        }
        // ... 每个工具: 反序列化 → 动态分级 → 权限检查 → 执行
        _ => Err(format!("unsupported tool: {name}")),
    }
}
```

### 4.2 动态权限分级

部分工具按输入内容动态升级权限要求：

#### bash 权限分级 (`lib.rs:2190`)

```rust
fn classify_bash_permission(command: &str) -> PermissionMode {
    // 只读命令白名单: cat, head, tail, less, more, ls, grep, rg, awk, sed, file, stat, ...
    if READ_ONLY_COMMANDS.contains(&cmd_name) && !has_dangerous_paths(command) {
        return PermissionMode::WorkspaceWrite;
    }
    PermissionMode::DangerFullAccess
}
```

危险路径检测 (`has_dangerous_paths`):
- `$` 变量展开
- Windows 绝对路径 (`C:\...`)
- 工作区外的绝对路径
- `../..` 父目录穿越
- 指向工作区外的相对路径

#### read_file 权限分级 (`lib.rs:2562`)

```rust
fn classify_read_path_permission(path: &str, allow_missing: bool) -> PermissionMode {
    if path_within_current_workspace(path, allow_missing) {
        PermissionMode::ReadOnly
    } else {
        PermissionMode::DangerFullAccess  // 读 /etc/passwd 等外部路径
    }
}
```

#### write_file / edit_file 权限分级 (`lib.rs:2554`)

```rust
fn classify_file_path_permission(path: &str, allow_missing: bool) -> PermissionMode {
    if path_within_current_workspace(path, allow_missing) {
        PermissionMode::WorkspaceWrite
    } else {
        PermissionMode::DangerFullAccess  // 写工作区外
    }
}
```

### 4.3 `SubagentToolExecutor` — 子 Agent 执行器

**文件：** `lib.rs:5342-5376`

```rust
struct SubagentToolExecutor {
    allowed_tools: BTreeSet<String>,
    enforcer: Option<PermissionEnforcer>,
}

impl ToolExecutor for SubagentToolExecutor {
    fn execute(&mut self, tool_name: &str, input: &str) -> Result<String, ToolError> {
        // 1. 白名单检查
        if !self.allowed_tools.contains(&canonical_allowed_tool_name(tool_name)) {
            return Err(ToolError::new("tool not enabled for this sub-agent"));
        }
        // 2. 反序列化 + 内置执行
        let value = serde_json::from_str(input)?;
        execute_tool_with_enforcer(self.enforcer.as_ref(), tool_name, &value)
            .map_err(ToolError::new)
    }
}
```

### 4.4 `ToolExecutor` trait

**文件：** `rust/crates/runtime/src/conversation.rs:62`

```rust
pub trait ToolExecutor {
    fn execute(&mut self, tool_name: &str, input: &str) -> Result<String, ToolError>;
}
```

会话运行时通过 `self.tool_executor.execute(&tool_name, &input)` 统一调用，不关心工具来源。

---

## 五、各工具具体实现

### 5.1 bash — Shell 命令

**实现：** `rust/crates/runtime/src/bash.rs:72`

```
run_bash(input)
  ├─ workspace_test_branch_preflight(command)
  │    检测 "cargo test --workspace" 等测试命令
  │    检查当前分支是否落后 main → 落后则短路返回警告
  │
  └─ execute_bash(input)
       ├─ run_in_background=true → spawn 子进程, stdio=null, 返回 PID
       └─ 否则:
            ├─ detect_and_emit_ship_prepared (git push main 检测)
            ├─ prepare_tokio_command (构建 tokio::Command)
            ├─ timeout.map_or(直接 await, tokio::time::timeout)
            ├─ truncate_output → 截断超长输出
            └─ BashCommandOutput { stdout, stderr, exit_code, ... }
```

### 5.2 read_file — 读文件

**实现：** `rust/crates/runtime/src/file_ops.rs:185`

```
normalize_path(path) → 解析 ../, canonicalize
  → fs::metadata → 大小 > MAX_READ_SIZE (10MB) → 拒绝
  → is_binary_file() → 读前 8192 字节, 含 NUL → 拒绝
  → fs::read_to_string → 按 offset/limit 切片
  → ReadFileOutput { filePath, content, numLines, startLine, totalLines }
```

### 5.3 write_file — 写文件

**实现：** `rust/crates/runtime/src/file_ops.rs:234`

```
normalize_path_allow_missing(path) → canonicalize
  → content.len() > MAX_WRITE_SIZE (10MB) → 拒绝
  → 读旧文件 (fs::read_to_string, 允许不存在)
  → fs::create_dir_all(parent)
  → fs::write(path, content)
  → make_patch(old, new) → 生成 structured_patch (unified diff hunks)
  → kind: "create" | "update"
```

### 5.4 edit_file — 字符串替换编辑

**实现：** `rust/crates/runtime/src/file_ops.rs:268`

```
normalize_path → fs::read_to_string (必须存在)
  → old_string == new_string → 报错
  → !original.contains(old_string) → 报错 "old_string not found"
  → replace_all ? str::replace : str::replacen(..., 1)
  → fs::write → make_patch(old, new)
  → EditFileOutput { filePath, oldString, newString, structuredPatch, replaceAll, ... }
```

### 5.5 glob_search — Glob 文件搜索

**实现：** `rust/crates/runtime/src/file_ops.rs:313`

```
expand_braces(pattern)          // {a,b} → [a, b]
  → 对每个展开后的 pattern:
      Pattern::new(pat)          // glob crate
      → derive_glob_walk_root   // 找到不含通配符的最长前缀作为遍历根
      → WalkDir 遍历
      → 过滤: 跳过 .git, node_modules, .build, target, dist, coverage
      → Pattern::matches_path 匹配
      → HashSet 去重
  → 按修改时间降序 (Reverse)
  → 截断至 100 条
  → GlobSearchOutput { durationMs, numFiles, filenames, truncated }
```

### 5.6 grep_search — 内容搜索

**实现：** `rust/crates/runtime/src/file_ops.rs:395`

```
RegexBuilder::new(pattern)
    .case_insensitive / .dot_matches_new_line
  → collect_search_files(base_path)  // 收集目录下所有文件
  → 对每个文件:
      可选 glob_filter → 文件名过滤
      可选 file_type    → 扩展名过滤 (--type)
      fs::read_to_string → regex.find_iter / is_match
      三种输出模式:
        "files_with_matches" → 只收集文件名列表
        "count"              → 文件名 + 匹配次数
        "content"            → 文件名 + 带行号 + before/after/context 的匹配行
                              (line_numbers 默认 true)
  → offset + head_limit 分页
  → GrepSearchOutput { mode, numFiles, filenames, content, numMatches, ... }
```

### 5.7 WebFetch — 网页抓取

**实现：** `lib.rs:3355`

```
build_http_client()            // reqwest, 20s timeout, max 10 redirects
  → normalize_fetch_url(url)   // HTTP → HTTPS 自动升级 (非 localhost)
  → client.get(url).send()
  → normalize_fetched_content:
      html → html_to_text()    // 标签剥离, 保留纯文本
      其他 → 直接保留
  → summarize_web_fetch:
      prompt 含 "title"    → 提取 <title> 标签内容
      prompt 含 "summary"  → 前 900 字符预览
      其他                  → "Prompt: ...\nContent preview:\n..."
  → WebFetchOutput { bytes, code, url, result, duration_ms }
```

### 5.8 WebSearch — 网页搜索

**实现：** `lib.rs:3389`

```
build_search_url(query)
  → CLAWD_WEB_SEARCH_BASE_URL 环境变量 (自定义搜索引擎)
  → fallback: https://html.duckduckgo.com/html/?q=<query>
  → client.get() → extract_search_hits(html) → 解析搜索结果链接
  → 若空 → extract_search_hits_from_generic_links(html) → 泛化链接提取
  → allowed_domains 白名单 / blocked_domains 黑名单过滤
  → dedupe_hits → 截断至 8 条
  → 渲染为 markdown link 列表: "- [title](url)"
```

### 5.9 TodoWrite — 任务列表

**实现：** `lib.rs:3744`

```
validate_todos:
  - todos 非空
  - 每个 content 非空
  - 每个 activeForm 非空

todo_store_path() → .clawd-todos.json (或 CLAWD_TODO_STORE 环境变量)
  → 读取旧 todos
  → 所有 status=completed → 清空文件 (不存空列表)
  → 否则覆盖写入

verification_nudge_needed:
  全部完成 + ≥3 条 + 无任何 "verif" 关键词 → true
  (提醒模型检查是否真的完成了)
```

### 5.10 Skill — 技能加载

**实现：** `lib.rs:3790`

```
resolve_skill_path(skill):
  → commands::resolve_skill_path()     // 项目 .claude/skills/ 目录
  → fallback: skill_lookup_roots() 遍历:
      项目根:
        .claude/skills/
        .claude/commands/               (legacy)
      用户级:
        CLAW_CONFIG_HOME/skills/
        CODEX_HOME/skills/
        HOME/.claude/skills/
        HOME/.claude/commands/          (legacy)
        CLAUDE_CONFIG_DIR/skills/
        CLAUDE_CONFIG_DIR/skills/omc-learned/

  → fs::read_to_string(skill_path)
  → parse_skill_description(prompt)     // 提取描述行
  → SkillOutput { skill, path, args, description, prompt }
```

### 5.11 Agent — 子 Agent 启动

**实现：** `lib.rs:4095`

```
execute_agent(input):
  → description/prompt 非空验证
  → make_agent_id() (随机 hex)
  → agent_store_dir() → .clawd-agents/ 目录
  → 写 output_file (markdown 任务描述)
  → build_agent_system_prompt(subagent_type, model)
     从 commands 目录加载对应类型的系统提示
  → allowed_tools_for_subagent(subagent_type)
     Plan agent → ReadOnly 级工具
     general-purpose → 全部工具
     ...
  → 写 AgentOutput manifest JSON
  → spawn_agent_job():
      std::thread::Builder → 新线程
      → run_agent_job:
          API 调用循环:
            request → 解析响应 → tool_use?
              → SubagentToolExecutor.execute()
              → tool_result → 追加到对话
            → 模型停止 → 持久化结果
          panic catch → persist_agent_terminal_state("failed")
  → AgentOutput { agent_id, name, status: "running", output_file, ... }
```

### 5.12 NotebookEdit — Jupyter Notebook 编辑

**实现：** `lib.rs:5733`

```
验证: 扩展名 = .ipynb
  → serde_json::from_str → notebook JSON

三种模式:
  Insert (在 cell_id 之后插入):
    → make_cell_id → build_notebook_cell(code/markdown)
    → cells.insert(insert_at)

  Delete:
    → 验证有 cell_id → cells.remove(idx)

  Replace:
    → 验证有 cell_id → cells[idx]["source"] = 新 source_lines
    → Code:   确保有 outputs[], execution_count
    → Markdown: 移除 outputs, execution_count

  → serde_json::to_string_pretty → fs::write
  → NotebookEditOutput { cell_id, cell_type, language, ... }
```

### 5.13 EnterPlanMode / ExitPlanMode

**实现：** `lib.rs:6013, 6082`

使用 worktree-local `settings.json` 做状态机：

```
EnterPlanMode:
  1. 读 settings.json → 当前 permissions.defaultMode 值
  2. 已是 "plan" → no-op 返回
  3. 写 PlanModeState { had_local_override, previous_local_mode } 到 state 文件
  4. 写 settings.json: permissions.defaultMode = "plan"

ExitPlanMode:
  1. 读 state 文件 (无 state → no-op)
  2. 当前不是 "plan" → 清理 stale state
  3. 从 state 恢复 previous_local_mode:
     - 有值 → 设回 settings.json
     - 无值 → 删除 permissions.defaultMode key
  4. 删除 state 文件
```

### 5.14 REPL — 代码执行

**实现：** `lib.rs:6165`

```
resolve_repl_runtime(language):
  python/py → python3 -c  (优先 python3, fallback python)
  node/js   → node -e
  ruby/rb   → ruby -e
  sh/bash   → sh -c
  ...

→ Command::new(program).args(args).arg(code)
  timeout 模式: 轮询 try_wait() + 10ms sleep, 超时 → kill()
  无 timeout:   直接 wait_with_output()
→ ReplOutput { language, stdout, stderr, exit_code, duration_ms }
```

### 5.15 PowerShell — Windows Shell

**实现：** `lib.rs:6566`

```
detect_powershell_shell() → pwsh 优先, fallback powershell
  → execute_shell_command(shell, command, timeout, background):
      后台: spawn 子进程, stdio=null, 返回 PID
      同步: pwsh -NoProfile -NonInteractive -Command <command>
             超时轮询 + kill
```

### 5.16 Sleep — 休眠

**实现：** `lib.rs:5903`

```
duration_ms > 300_000 (5分钟) → 拒绝
std::thread::sleep(Duration::from_millis(duration_ms))
```

### 5.17 AskUserQuestion — 交互提问

**实现：** `lib.rs:1525`

```
writeln!(stdout, "[Question] ...")
  → 有选项: 列出 "1. opt1\n2. opt2" → "Enter choice (1-N): "
  → 无选项: "Your answer: "
  → stdin.read_line → trim
  → 有选项: 解析数字 → 取对应选项文本
  → { question, answer, status: "answered" }
```

### 5.18 Config — 设置读写

**实现：** `lib.rs:5964`

```
supported_config_setting(setting) → 查表得 (scope, json_path)
  不认识的 setting → { success: false, error: "Unknown setting" }

  get (无 value): get_nested_value(document, path)
  set (有 value): normalize_config_value → set_nested_value → 写回 JSON
```

### 5.19 SendUserMessage / Brief

**实现：** `lib.rs:5917`

```
message 非空验证
  → resolve_attachment(path):
      canonicalize → metadata.len → is_image? (png/jpg/jpeg/gif/webp/bmp/svg)
  → BriefOutput { message, attachments, sent_at }
```

### 5.20 StructuredOutput

**实现：** `lib.rs:6153`

```
payload 非空验证 → 直接透传
→ StructuredOutputResult { data, structured_output }
```

### 5.21 Git 工具系列

| 工具 | 实现逻辑 |
|---|---|
| `GitStatus` | `git status --short --branch` |
| `GitDiff` | `git diff [--cached] [commit] [commit2] [-- path]` |
| `GitLog` | `git log -n{count(default=20)} [--oneline] [--author=] [--since=] [--until=] [-- path]` |
| `GitShow` | `git show [--format=patch\|stat\|metadata] [commit[:path]]` |
| `GitBlame` | `git blame [commit] [-- path]` |

所有 Git 工具通过 `git_stdout(&args)` 辅助函数 (`runtime/src/lib.rs`) 调用，失败返回描述性错误。

### 5.22 Task / Worker / Team / Cron 工具

这些是对全局 `OnceLock` 注册中心的 CRUD 包装：

```
TaskCreate    → global_task_registry().create(prompt, description)
TaskGet       → global_task_registry().get(task_id) → 返回任务详情
TaskList      → global_task_registry().list() → JSON 数组
TaskStop      → global_task_registry().stop(task_id)
TaskUpdate    → global_task_registry().update(task_id, message)
TaskOutput    → global_task_registry().output(task_id) → 返回输出文本

WorkerCreate           → registry.create(cwd, trusted_roots, auto_recover)
WorkerGet              → registry.get(worker_id)
WorkerObserve          → registry.observe(worker_id, screen_text)
WorkerResolveTrust     → registry.resolve_trust(worker_id)
WorkerAwaitReady       → registry.await_ready(worker_id)
WorkerSendPrompt       → registry.send_prompt(worker_id, prompt, task_receipt)
WorkerRestart          → registry.restart(worker_id)
WorkerTerminate        → registry.terminate(worker_id)
WorkerObserveCompletion → registry.observe_completion(worker_id, finish_reason, tokens)

TeamCreate → registry.create(name, task_ids, strategy, ...)
TeamDelete → registry.delete(team_id)

CronCreate → registry.create(schedule, prompt, description)
CronDelete → registry.delete(cron_id)
CronList   → registry.list(false) → JSON 数组
```

### 5.23 MCP / LSP 工具

```
LSP → global_lsp_registry().dispatch(action, path, line, character, query)
       action: "hover", "definition", "references", "completion", "symbols", ...

MCP → global_mcp_registry().call_tool(server, tool_name, arguments)
      通过 MCP bridge 向连接的 MCP server 发起 tool call

ListMcpResources → registry.list_resources(server)
ReadMcpResource  → registry.read_resource(server, uri)
McpAuth          → 触发 MCP server 的 OAuth 认证流程
```

---

## 六、完整调用链路图

```
┌─────────────────────────────────────────────────────────────┐
│ API 响应: { "type": "tool_use", "name": "bash", "input": "…" } │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ ConversationRuntime                                         │
│   self.tool_executor.execute("bash", &input_str)            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ GlobalToolRegistry.execute("bash", input)                   │
│   ├─ 查找: mvp_tool_specs() 中存在 → 走内置路径               │
│   └─ execute_tool_with_enforcer(enforcer, "bash", input)     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ execute_tool_with_enforcer("bash", input)                   │
│   1. from_value::<BashCommandInput>(input)                  │
│   2. classify_bash_permission(command)                      │
│      → read-only 命令 + 安全路径 → WorkspaceWrite            │
│      → 其他 → DangerFullAccess                               │
│   3. enforcer.check_with_required_mode(name, input, mode)   │
│      → Allowed / Denied                                     │
│   4. run_bash(input)                                        │
│      → execute_bash() → Command::new().output()             │
│      → to_pretty_json(BashCommandOutput)                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 返回 Result<String, String>                                 │
│ ConversationRuntime 将其包装为 ToolResultContentBlock         │
│ 追加到对话历史 → 发送下一轮 API 请求                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 七、关键数据流

### 7.1 工具 input 反序列化

每种工具的 input 都有对应的 `struct` 和 `from_value`：

```rust
// 通过 serde_json::from_value 泛型实现
fn from_value<T: DeserializeOwned>(value: &Value) -> Result<T, String> {
    T::deserialize(value).map_err(|e| e.to_string())
}

// bash 的 input 结构
struct BashCommandInput {
    command: String,
    timeout: Option<u64>,
    description: Option<String>,
    run_in_background: Option<bool>,
    dangerouslyDisableSandbox: Option<bool>,
    // ...
}
```

### 7.2 工具 output 序列化

所有工具输出通过 `to_pretty_json` 序列化为字符串返回给模型：

```rust
fn to_pretty_json<T: Serialize>(value: T) -> Result<String, String> {
    serde_json::to_string_pretty(&value).map_err(|e| e.to_string())
}
```

### 7.3 权限检查的两种方式

**静态权限**（大部分工具）：
```rust
// 直接用 ToolSpec.required_permission
maybe_enforce_permission_check_with_mode(enforcer, name, input, PermissionMode::DangerFullAccess)?;
```

**动态权限**（bash, read_file, write_file, edit_file, glob_search, grep_search, PowerShell）：
```rust
// 先按输入内容动态分级
let classified = classify_bash_permission(&bash_input.command);
// 再以分级后的权限检查
maybe_enforce_permission_check_with_mode(enforcer, name, input, classified)?;
```

---

## 八、工作区边界保护

**文件：** `rust/crates/runtime/src/file_ops.rs:42, 183`

所有文件操作都有两层保护：

**第一层：路径解析规范化**
```rust
fn normalize_path(path: &str) -> io::Result<PathBuf> {
    // 解析 ../ 为绝对路径
    // canonicalize → 跟随 symlink 解析
    // 验证 starts_with(workspace_root)
}
```

**第二层：PermissionEnforcer 文件操作检查**
```rust
// permission_enforcer.rs:108
fn check_file_write(path: &str, workspace_root: &str) -> EnforcementResult {
    match mode {
        PermissionMode::ReadOnly => Deny("file writes not allowed"),
        PermissionMode::WorkspaceWrite => {
            if is_within_workspace(path, workspace_root) {
                Allowed
            } else {
                Deny("path outside workspace")
            }
        }
        Allow | DangerFullAccess => Allowed,
    }
}
```

**路径穿越防护** (`permission_enforcer.rs:183`)：
```rust
fn is_within_workspace(path: &str, workspace_root: &str) -> bool {
    // lexically_normalize: 解析 . 和 .. 组件，../.. 不能逃逸
    // 结果必须是 workspace_root 或 workspace_root/ 的子路径
}
```

---

## 九、复刻要点

1. **工具定义集中化**：所有工具在一个 `mvp_tool_specs()` 中声明，统一管理 name/description/schema/permission
2. **权限系统分层**：5 级 enum + PartialOrd derive，核心判断只有 `current >= required`
3. **动态分级是关键创新**：同一工具不同输入触发不同权限，bash 是典型例子
4. **三层注册体系**：内置 + 插件 + (MCP)运行时，`--allowedTools` 白名单过滤
5. **巨型 match 分发**：简单粗暴但清晰，每个工具有独立的类型化 input/output
6. **工作区边界双重保护**：文件操作层 + 权限执法层各自校验路径
7. **ToolExecutor trait**：解耦会话运行时和具体工具执行器
8. **全局 OnceLock 注册中心**：Task/Worker/Cron 用静态单例跨工具共享状态
9. **Plan 模式是配置层的状态机**：通过动态写 `settings.json` + state 文件实现 enter/exit
10. **Agent 启动是线程 spawn + API 循环**：子 agent 在新线程中用受限工具集独立运行
