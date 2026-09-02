export const inspector = {
  openFunctionality: "Open functionality",
  selectFunctionality: "Select functionality",
  home: "Home",
  taskSummary: "Task summary",
  browser: "Browser",
  terminal: "Terminal",
  files: "Files",
  openTabsAria: "Open features",
  newBrowserTab: "New tab",
  newBrowserTabAria: "New browser tab",
  exitFullscreen: "Exit fullscreen",
  enterFullscreen: "Enter fullscreen",
  exitSplitScreen: "Exit split-screen layout",
  startHere: "Start here",
  projectProfile: {
    title: "Project profile",
    basedOnStructure: "Based on workspace structure",
    basedOnStructureHint: "Suggestion only, not executed; actual runs still require tool permissions and approval.",
    refresh: "Refresh project profile",
    refreshing: "Refreshing…",
    loading: "Detecting project structure",
    error: {
      refreshFailedStillShow: "Refresh failed, still showing last detection result: ",
      loadFailed: "Project profile load failed: "
    },
    meta: {
      rootDir: "Root directory",
      monorepo: "Monorepo",
      scanLimited: "Scan scope limited, results may be incomplete"
    },
    overview: {
      projects: "Projects",
      technologies: "Technologies",
      validations: "Validation suggestions",
      evidence: "Detection evidence"
    },
    component: {
      workspaceRoot: "Workspace root",
      relativePath: "Relative path",
      technologies: "Technology detection",
      techItem: " results",
      notIdentified: "Not identified",
      confidence: {
        confirmed: "Confirmed",
        maybe: "Maybe"
      },
      recommendedValidations: "Recommended validations",
      category: " categories",
      commands: " commands",
      workingDirectory: "Directory: ",
      basedOn: "Based on: ",
      validationEmpty: "No reliable validation commands suggested for current structure.",
      validationHint: "Above commands are suggestions only, not executed automatically.",
      evidenceList: "Detection evidence (",
      evidenceCountEnd: ")"
    },
    empty: {
      title: "No project profile",
      hint: "Click “Refresh project profile” to re-detect current workspace."
    }
  },
  todo: {
    title: "Todo",
    progressAria: "Progress {completed}/{total}",
    empty: {
      title: "No todos",
      hint: "Progress of complex tasks will appear here"
    }
  },
  artifacts: {
    title: "Task artifacts",
    itemCount: " items",
    codeChange: "Code change",
    taskAttachment: "Task attachment",
    preview: {
      title: "View other attachments",
      close: "Close preview"
    },
    refresh: "Refresh artifacts",
    empty: {
      title: "No artifacts",
      hint: "Files generated after task completion will appear here"
    }
  },
  references: {
    title: "References",
    skills: "Skills",
    context: "Context",
    currentProject: "Current project",
    noSkills: "No skills loaded for this task",
    relatedItemsCount: "{count} related items",
    relatedItemsHint: "{attachments} attachments · {changes} file changes"
  },
  browserToolbar: {
    ariaLabel: "Web navigation",
    back: "Back",
    forward: "Forward",
    refresh: "Refresh page",
    addressPlaceholder: "Enter URL",
    visitUrl: "Visit URL",
    moreOptions: "More options",
    empty: "No web preview yet, let AI generate some content!",
    loading: "Loading webpage",
    urlError: "Please enter a valid URL",
    loadError: "Failed to load webpage: "
  },
  fileTree: {
    openWithExternalApp: "Open with external app",
    closeTab: "Close",
    collapseTree: "Collapse file tree",
    expandTree: "Expand file tree",
    previewError: {
      title: "Cannot preview file"
    },
    previewPlaceholder: {
      title: "Open a file",
      hint: "Select a file from workspace directory tree"
    },
    divider: "Drag to adjust file tree width",
    loading: "Loading…",
    emptyDir: "Directory is empty",
    errors: {
      fileNotExist: "File doesn't exist: {path}",
      permissionDenied: "No permission to read file: {path}",
      isDirectory: "Path is a directory, not a file: {path}",
      fallback: "Cannot read file: {path}"
    },
    truncated: "Only first 1 MB shown",
    binary: "Cannot preview binary file",
    binaryHint: "This file is not a displayable text format"
  },
  workContext: {
    title: "Task progress & context",
    progress: "Progress",
    progressPercent: "{percent}%",
    context: "Context",
    expandNMore: "Expand {n} more",
    collapse: "Collapse",
    contextEmpty: {
      title: "Task plan will appear here",
      fileEmpty: "Related files will appear here"
    }
  },
  richFilePreview: {
    previewMode: "Preview mode",
    preview: "Preview",
    source: "Source",
    truncatedHint: "File too big, preview may be incomplete",
    imageFailed: "Image unavailable: {path}"
  },
  common: {
    openChangesPanel: "Open changes panel",
    openFileInWorkspace: "Open file in workspace"
  }
};
