export const workflow = {
  title: "工作流",
  page: {
    title: "工作流管理",
    subtitle: "定义任务自动化序列",
    empty: "暂无工作流",
    createNew: "创建新工作流",
    list: {
      name: "名称",
      description: "描述",
      lastRun: "上次运行",
      run: "运行",
      edit: "编辑",
      delete: "删除",
      deleteConfirm: "删除工作流「{name}」？此操作不可撤销。"
    }
  },
  graph: {
    ariaLabel: "工作流图",
    node: {
      start: "开始",
      end: "结束",
      task: "任务",
      condition: "条件",
      parallel: "并行",
      delay: "延迟",
      trigger: "触发器"
    },
    edge: {
      onSuccess: "成功时",
      onFailure: "失败时",
      always: "始终"
    },
    toolbar: {
      zoomIn: "放大",
      zoomOut: "缩小",
      resetZoom: "重置缩放",
      pan: "平移",
      fitToView: "适应视图",
      addNode: "添加节点",
      connectNodes: "连接节点",
      deleteNode: "删除节点",
      editNode: "编辑节点"
    },
    empty: "拖放节点开始构建",
    save: "保存",
    saveAs: "另存为",
    name: "工作流名称",
    description: "描述（可选）",
    namePlaceholder: "我的工作流",
    descPlaceholder: "描述这个工作流做什么"
  },
  common: {
    save: "保存",
    cancel: "取消",
    delete: "删除",
    edit: "编辑",
    create: "创建",
    run: "运行",
    stop: "停止",
    confirm: "确认",
    close: "关闭"
  }
};
