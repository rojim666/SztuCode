export const workflow = {
  title: "Workflow",
  page: {
    title: "Workflow management",
    subtitle: "Define automated task sequences",
    empty: "No workflows yet",
    createNew: "Create new workflow",
    list: {
      name: "Name",
      description: "Description",
      lastRun: "Last run",
      run: "Run",
      edit: "Edit",
      delete: "Delete",
      deleteConfirm: "Delete workflow “{name}”? This action cannot be undone."
    }
  },
  graph: {
    ariaLabel: "Workflow graph",
    node: {
      start: "Start",
      end: "End",
      task: "Task",
      condition: "Condition",
      parallel: "Parallel",
      delay: "Delay",
      trigger: "Trigger"
    },
    edge: {
      onSuccess: "On success",
      onFailure: "On failure",
      always: "Always"
    },
    toolbar: {
      zoomIn: "Zoom in",
      zoomOut: "Zoom out",
      resetZoom: "Reset zoom",
      pan: "Pan",
      fitToView: "Fit to view",
      addNode: "Add node",
      connectNodes: "Connect nodes",
      deleteNode: "Delete node",
      editNode: "Edit node"
    },
    empty: "Drag and drop nodes to start building",
    save: "Save",
    saveAs: "Save as",
    name: "Workflow name",
    description: "Description (optional)",
    namePlaceholder: "My workflow",
    descPlaceholder: "Describe what this workflow does"
  },
  common: {
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    edit: "Edit",
    create: "Create",
    run: "Run",
    stop: "Stop",
    confirm: "Confirm",
    close: "Close"
  }
};
