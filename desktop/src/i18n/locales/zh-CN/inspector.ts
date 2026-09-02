export const inspector = {
  openFunctionality: "打开功能",
  selectFunctionality: "选择功能",
  home: "首页",
  taskSummary: "任务摘要",
  browser: "浏览器",
  terminal: "终端",
  files: "文件",
  openTabsAria: "已打开功能",
  newBrowserTab: "新标签页",
  newBrowserTabAria: "新建浏览器标签页",
  exitFullscreen: "退出全屏",
  enterFullscreen: "全屏",
  exitSplitScreen: "退出分屏布局",
  startHere: "从这里开始",
  projectProfile: {
    title: "项目画像",
    basedOnStructure: "基于工作区结构生成",
    basedOnStructureHint: "仅建议，未执行；实际运行仍需经过工具权限与审批。",
    refresh: "刷新项目画像",
    refreshing: "正在刷新",
    loading: "正在识别项目结构",
    error: {
      refreshFailedStillShow: "刷新失败，仍显示上次检测结果：",
      loadFailed: "项目画像加载失败："
    },
    meta: {
      rootDir: "根目录",
      monorepo: "Monorepo",
      scanLimited: "扫描范围受限，结果可能不完整"
    },
    overview: {
      projects: "项目",
      technologies: "技术项",
      validations: "验证建议",
      evidence: "识别证据"
    },
    component: {
      workspaceRoot: "工作区根目录",
      relativePath: "相对路径",
      technologies: "技术识别",
      techItem: "项结果",
      notIdentified: "未识别",
      confidence: {
        confirmed: "已确认",
        maybe: "可能"
      },
      recommendedValidations: "推荐验证",
      category: "类",
      commands: "条命令",
      workingDirectory: "目录：",
      basedOn: "依据：",
      validationEmpty: "当前结构下暂无可靠的验证命令建议。",
      validationHint: "以上命令仅作为验证建议，不会自动执行。",
      evidenceList: "识别证据（",
      evidenceCountEnd: "）"
    },
    empty: {
      title: "暂无项目画像",
      hint: "可点击“刷新项目画像”重新检测当前工作区。"
    }
  },
  todo: {
    title: "待办",
    progressAria: "进度 {completed}/{total}",
    empty: {
      title: "暂无待办",
      hint: "复杂任务的进展会显示在这里"
    }
  },
  artifacts: {
    title: "任务产物",
    itemCount: "项",
    codeChange: "代码变更",
    taskAttachment: "任务附件",
    preview: {
      title: "查看其他附件",
      close: "关闭预览"
    },
    refresh: "刷新产物",
    empty: {
      title: "暂无产物",
      hint: "任务完成后，生成的文件将展示在这里"
    }
  },
  references: {
    title: "参考信息",
    skills: "技能",
    context: "上下文",
    currentProject: "当前项目",
    noSkills: "本轮任务暂未加载技能",
    relatedItemsCount: "{count} 项关联内容",
    relatedItemsHint: "{attachments} 个附件 · {changes} 个文件变更"
  },
  browserToolbar: {
    ariaLabel: "网页导航",
    back: "后退",
    forward: "前进",
    refresh: "刷新网页",
    addressPlaceholder: "输入 URL",
    visitUrl: "访问网页",
    moreOptions: "更多选项",
    empty: "暂无网页预览，让AI生成一些内容看看吧！",
    loading: "正在载入网页",
    urlError: "请输入有效的网址",
    loadError: "网页加载失败："
  },
  fileTree: {
    openWithExternalApp: "使用外部应用打开",
    closeTab: "关闭",
    collapseTree: "折叠文件树",
    expandTree: "展开文件树",
    previewError: {
      title: "无法预览文件"
    },
    previewPlaceholder: {
      title: "打开文件",
      hint: "从工作区目录树中选择文件"
    },
    divider: "拖拽调整文件树宽度",
    loading: "加载中…",
    emptyDir: "目录为空",
    errors: {
      fileNotExist: "文件不存在：{path}",
      permissionDenied: "无权限读取文件：{path}",
      isDirectory: "路径是目录而非文件：{path}",
      fallback: "无法读取文件：{path}"
    },
    truncated: "仅显示前 1 MB",
    binary: "无法预览二进制文件",
    binaryHint: "该文件不是可显示的文本格式"
  },
  workContext: {
    title: "任务进度与上下文",
    progress: "进度",
    progressPercent: "{percent}%",
    context: "上下文",
    expandNMore: "展开 {n} 个",
    collapse: "收起",
    contextEmpty: {
      title: "任务计划会显示在这里",
      fileEmpty: "相关文件会显示在这里"
    }
  },
  richFilePreview: {
    previewMode: "预览方式",
    preview: "预览",
    source: "源码",
    truncatedHint: "文件过大，预览可能不完整",
    imageFailed: "图片不可用：{path}"
  },
  common: {
    openChangesPanel: "打开变更面板",
    openFileInWorkspace: "在工作区中打开文件"
  }
};
