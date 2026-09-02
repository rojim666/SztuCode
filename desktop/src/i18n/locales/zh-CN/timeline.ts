/** 时间线/执行过程组件群文案（timeline.*）。 */
export const timeline = {
  /** 用时 */
  elapsed: "耗时 {duration}",
  duration: {
    seconds: "{n} 秒",
    minutesSeconds: "{m} 分 {s} 秒",
    minutes: "{m} 分钟",
  },
  /** 轮次状态与过程切换 */
  turn: {
    failed: "失败",
    interrupted: "已中断",
    collapse: "收起过程",
    view: "查看过程 · {duration}",
    modelUnrecorded: "未记录模型",
  },
  /** 计划进度 */
  progress: {
    step: "步骤 {current} / {total}",
    done: "完成 {completed} / {total} 个步骤",
  },
  planningNext: "正在规划下一步",
  /** 轮内操作按钮 */
  action: {
    copied: "已复制",
    copySummary: "复制整段总结",
    copiedSummary: "已复制总结",
    retry: "回退本次修改并重新执行",
    continueTitle: "从中断处继续执行",
    continue: "继续执行",
  },
  /** Token 用量 */
  usage: {
    aria: "本轮 Token 消耗与缓存命中",
    cache: "缓存",
    input: "输入",
    output: "输出",
  },
  /** 验证与变更证据条 */
  evidence: {
    aria: "验证与变更",
    passedSuffix: "项验证通过",
    failedSuffix: "项验证失败",
  },
  /** 轮次时序指标 */
  tail: {
    aria: "本轮时序指标",
    ttft: "首字",
    throughput: "吞吐",
  },
  /** 思考面板 */
  thinking: {
    label: "思考",
    /** ThinkingPanel 折叠行标签（现状为英文，保持一致） */
    think: "Think",
    current: "当前判断",
    notes: "过程说明",
  },
  /** 活动块（思考+工具折叠行） */
  activity: {
    failHint: "有操作失效，点击查看",
    toolCalls: "工具调用",
    toolKind: {
      read: "读取",
      search: "搜索",
      edit: "编辑",
      exec: "执行",
      call: "调用",
      operate: "操作",
    },
  },
  /** 行为目的推断 */
  purpose: {
    view: "查看 {name}",
    readFile: "读取文件",
    search: "搜索 \"{query}\"",
    searchCode: "搜索相关代码",
    modify: "修改 {name}",
    editFile: "编辑文件",
    execCommand: "执行命令",
  },
  /** 展开态明细区块标题 */
  details: {
    plan: "计划",
    tests: "测试",
    changes: "变更",
    agents: "Agent 集群",
    agentRunning: "运行中",
    agentDone: "完成",
    agentFailed: "失败",
    workflowTasks: "多智能体任务图",
    dependencies: "依赖 {deps}",
    handoffs: "结构化交接",
    scopeEscalations: "已审批范围升级：{items}",
    reviews: "Reviewer 仲裁",
    accept: "接受",
    return: "退回",
    diff: "Diff：",
    test: "测试：",
    security: "安全：",
    skills: "技能",
    logs: "日志",
  },
  /** 工具调用卡片 */
  tool: {
    title: {
      editing: "正在编辑 {target}",
      edited: "已编辑 {target}",
      searching: "正在搜索 {target}",
      searched: "已搜索 {target}",
      reading: "正在读取 {target}",
      read: "已读取 {target}",
      running: "正在{target}",
      done: "已{target}",
    },
    outputTruncated: "[... 省略 {lines} 行 / {chars} 字符 ...]",
    expandOutput: "展开查看完整输出",
    collapseOutput: "收起完整输出",
    params: "参数",
    input: "输入",
    output: "返回",
    screenshots: "截图",
    screenshotCount: "{count} 张截图",
    screenshotAlt: "页面截图 {index}",
  },
  /** 工具摘要行（按类型分组的 chip 文案） */
  toolSummary: {
    read: {
      running: "正在读取文件...",
      counting: "正在读取文件 {count} 个文件",
      done: "已读取文件 {count} 个文件",
    },
    search: {
      running: "正在搜索文件...",
      counting: "正在搜索文件 {count} 次",
      done: "已搜索文件 {count} 次",
    },
    edit: {
      running: "正在编辑文件...",
      counting: "正在编辑文件 {count} 个文件",
      done: "已编辑文件 {count} 个文件",
    },
    exec: {
      running: "正在执行命令...",
      counting: "正在执行命令 {count} 条命令",
      done: "已执行命令 {count} 条命令",
    },
    other: {
      running: "正在调用工具...",
      counting: "正在调用工具 {count} 个工具",
      done: "已调用工具 {count} 个工具",
    },
  },
  /** 会话统计行 */
  stats: {
    aria: "会话统计",
    turnsSteps: "{turns} 轮 · {steps} 步",
    ttft: "首 token 平均 {duration} · {speed} tok/s",
    cacheHit: "缓存命中 {percent}%",
    tokens: "输入 {input} tok · 输出 {output} tok",
    context: "上下文 {percent}%",
    contextTip: "上下文占用",
    contextTipDetail: "上下文占用 {percent}%\n系统 {system} · 摘要 {summary} · 会话 {conversation} · 工具 {tool}",
  },
  /** 上下文注入行 */
  context: {
    ariaLabel: "{label}（{source}）",
    chars: "{count}字符",
    filesCount: "{count}个文件",
    filesSection: "上下文文件",
    fileCount: "{count} 个",
    injectedContent: "注入内容",
    source: {
      intervention: "干预",
      steering: "追加",
      compaction: "压缩",
      canvas: "进度",
      system: "注入",
    },
  },
  /** 文件变更徽标 */
  changes: {
    filesSuffix: "个文件已更改",
    openAll: "在右侧查看所有变更",
  },
  /** 权限审批 */
  permission: {
    pending: "等待权限审批",
    granted: "已获批准",
    denied: "已拒绝",
    deny: "拒绝",
    allowOnce: "允许一次",
    moreOptions: "更多审批选项",
    alwaysAllow: "始终允许此工具",
    alwaysDeny: "始终拒绝此工具",
  },
  stepAria: "步骤 {step}",
  agentLogo: "SztuCode Agent",
  /** Markdown 文件链接 */
  fileLink: {
    open: "点击打开文件",
  },
  /** 链接右键菜单 */
  linkMenu: {
    openInApp: "在右侧浏览器栏打开",
    openInAppHint: "内置预览",
    openExternal: "在默认浏览器中打开",
    openExternalHint: "系统浏览器",
    copy: "复制链接地址",
  },
  /** 流水线阶段 */
  phase: {
    railAria: "执行阶段",
    understanding: "理解",
    understandingHint: "读取上下文、定位改动点",
    executing: "执行",
    executingHint: "写入与修改文件",
    verifying: "验证",
    verifyingHint: "跑测试、构建与静态检查",
    delivering: "交付",
    deliveringHint: "汇总本轮结果",
  },
  /** 流水线视图 */
  pipeline: {
    groupWrite: "修改了 {count} 个文件",
    groupVerify: "运行了 {count} 项检查",
    groupRead: "读取了 {count} 处上下文",
    groupExec: "执行了 {count} 条命令",
    thinking: "正在思考…",
    changedFiles: "· 改动 {count} 个文件",
    continue: "继续",
  },
};
