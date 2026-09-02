/** 时间线/执行过程组件群文案（timeline.*），结构与 zh-CN 完全一致。 */
export const timeline = {
  /** 用时 */
  elapsed: "Elapsed {duration}",
  duration: {
    seconds: "{n}s",
    minutesSeconds: "{m}m {s}s",
    minutes: "{m}m",
  },
  /** 轮次状态与过程切换 */
  turn: {
    failed: "Failed",
    interrupted: "Interrupted",
    collapse: "Collapse process",
    view: "View process · {duration}",
    modelUnrecorded: "Model not recorded",
  },
  /** 计划进度 */
  progress: {
    step: "Step {current} / {total}",
    done: "Completed {completed} / {total} steps",
  },
  planningNext: "Planning next step",
  /** 轮内操作按钮 */
  action: {
    copied: "Copied",
    copySummary: "Copy summary",
    copiedSummary: "Summary copied",
    retry: "Revert changes and rerun",
    continueTitle: "Continue from interruption",
    continue: "Continue",
  },
  /** Token 用量 */
  usage: {
    aria: "Token usage and cache hits for this turn",
    cache: "Cache",
    input: "Input",
    output: "Output",
  },
  /** 验证与变更证据条 */
  evidence: {
    aria: "Verification and changes",
    passedSuffix: "checks passed",
    failedSuffix: "checks failed",
  },
  /** 轮次时序指标 */
  tail: {
    aria: "Turn timing metrics",
    ttft: "First token",
    throughput: "Throughput",
  },
  /** 思考面板 */
  thinking: {
    label: "Thinking",
    /** ThinkingPanel 折叠行标签 */
    think: "Think",
    current: "Current reasoning",
    notes: "Process notes",
  },
  /** 活动块（思考+工具折叠行） */
  activity: {
    failHint: "Some operations failed, click to view",
    toolCalls: "Tool calls",
    toolKind: {
      read: "Read",
      search: "Search",
      edit: "Edit",
      exec: "Run",
      call: "Call",
      operate: "Actions",
    },
  },
  /** 行为目的推断 */
  purpose: {
    view: "View {name}",
    readFile: "Read file",
    search: "Search \"{query}\"",
    searchCode: "Search code",
    modify: "Modify {name}",
    editFile: "Edit file",
    execCommand: "Run command",
  },
  /** 展开态明细区块标题 */
  details: {
    plan: "Plan",
    tests: "Tests",
    changes: "Changes",
    agents: "Agent fleet",
    agentRunning: "Running",
    agentDone: "Done",
    agentFailed: "Failed",
    workflowTasks: "Agent task graph",
    dependencies: "Depends on {deps}",
    handoffs: "Structured handoffs",
    scopeEscalations: "Approved scope escalations: {items}",
    reviews: "Reviewer arbitration",
    accept: "Accept",
    return: "Return",
    diff: "Diff: ",
    test: "Tests: ",
    security: "Security: ",
    skills: "Skills",
    logs: "Logs",
  },
  /** 工具调用卡片 */
  tool: {
    title: {
      editing: "Editing {target}",
      edited: "Edited {target}",
      searching: "Searching {target}",
      searched: "Searched {target}",
      reading: "Reading {target}",
      read: "Read {target}",
      running: "Running {target}",
      done: "Ran {target}",
    },
    outputTruncated: "[... {lines} lines / {chars} chars omitted ...]",
    expandOutput: "Show full output",
    collapseOutput: "Collapse output",
    params: "Params",
    input: "Input",
    output: "Output",
    screenshots: "Screenshots",
    screenshotCount: "{count} screenshots",
    screenshotAlt: "Page screenshot {index}",
  },
  /** 工具摘要行（按类型分组的 chip 文案） */
  toolSummary: {
    read: {
      running: "Reading files...",
      counting: "Reading {count} files",
      done: "Read {count} files",
    },
    search: {
      running: "Searching...",
      counting: "Searching {count} times",
      done: "Searched {count} times",
    },
    edit: {
      running: "Editing files...",
      counting: "Editing {count} files",
      done: "Edited {count} files",
    },
    exec: {
      running: "Running commands...",
      counting: "Running {count} commands",
      done: "Ran {count} commands",
    },
    other: {
      running: "Calling tools...",
      counting: "Calling {count} tools",
      done: "Called {count} tools",
    },
  },
  /** 会话统计行 */
  stats: {
    aria: "Session stats",
    turnsSteps: "{turns} turns · {steps} steps",
    ttft: "Avg first token {duration} · {speed} tok/s",
    cacheHit: "Cache hit {percent}%",
    tokens: "Input {input} tok · Output {output} tok",
    context: "Context {percent}%",
    contextTip: "Context usage",
    contextTipDetail: "Context usage {percent}%\nSystem {system} · Summary {summary} · Conversation {conversation} · Tools {tool}",
  },
  /** 上下文注入行 */
  context: {
    ariaLabel: "{label} ({source})",
    chars: "{count} chars",
    filesCount: "{count} files",
    filesSection: "Context files",
    fileCount: "{count}",
    injectedContent: "Injected content",
    source: {
      intervention: "Intervention",
      steering: "Steering",
      compaction: "Compaction",
      canvas: "Progress",
      system: "Injection",
    },
  },
  /** 文件变更徽标 */
  changes: {
    filesSuffix: "files changed",
    openAll: "View all changes in the side panel",
  },
  /** 权限审批 */
  permission: {
    pending: "Awaiting approval",
    granted: "Approved",
    denied: "Denied",
    deny: "Deny",
    allowOnce: "Allow once",
    moreOptions: "More approval options",
    alwaysAllow: "Always allow this tool",
    alwaysDeny: "Always deny this tool",
  },
  stepAria: "Step {step}",
  agentLogo: "SztuCode Agent",
  /** Markdown 文件链接 */
  fileLink: {
    open: "Click to open file",
  },
  /** 链接右键菜单 */
  linkMenu: {
    openInApp: "Open in side browser",
    openInAppHint: "Built-in preview",
    openExternal: "Open in default browser",
    openExternalHint: "System browser",
    copy: "Copy link address",
  },
  /** 流水线阶段 */
  phase: {
    railAria: "Execution phases",
    understanding: "Understanding",
    understandingHint: "Reading context, locating changes",
    executing: "Executing",
    executingHint: "Writing and modifying files",
    verifying: "Verifying",
    verifyingHint: "Running tests, builds and static checks",
    delivering: "Delivering",
    deliveringHint: "Summarizing results",
  },
  /** 流水线视图 */
  pipeline: {
    groupWrite: "Edited {count} files",
    groupVerify: "Ran {count} checks",
    groupRead: "Read {count} context items",
    groupExec: "Ran {count} commands",
    thinking: "Thinking…",
    changedFiles: "· {count} files changed",
    continue: "Continue",
  },
};
