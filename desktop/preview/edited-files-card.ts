import { createApp, h, ref } from "vue";
import { i18n } from "../src/i18n";
import EditedFilesCard from "../src/components/timeline/EditedFilesCard.vue";
import DiffPreviewPopover from "../src/components/timeline/DiffPreviewPopover.vue";
import { parseDiffPreview } from "../src/utils/diffPreview";
import type { ChangeFile } from "../src/components/timeline/types";

const files: ChangeFile[] = [
  { path: "desktop/src/appearance.css", additions: 10, deletions: 0 },
  { path: "desktop/tests/visual/launcher-bottom-background.spec.ts", additions: 21, deletions: 0 },
];

const sampleDiff = [
  "@@ -903,10 +903,12 @@",
  " /* Only the visible card owns the fill, including in dark mode. */",
  "+.task-launcher .launcher-bottom-controls {",
  "+  margin-top: 0;",
  "+  padding-top: 10px;",
  "+  background: #f5f5f5;",
  "+  border-radius: 0 0 14px 14px;",
  "+}",
  '+:root[data-app-theme="dark"] .task-launcher .launcher-bottom-controls {',
  "+  background: #252525;",
  "+}",
  "+",
  '+:root:not([data-wallpaper="none"]) .task-conversation .sztu-composer:not(.drag-over) {',
].join("\n");

const previewLines = parseDiffPreview(sampleDiff);

const Demo = {
  setup() {
    const last = ref("");
    const stage = (theme: "light" | "dark") =>
      h("div", { class: "stage", "data-app-theme": theme }, [
        h("span", { class: "stage-label" }, theme),
        h(DiffPreviewPopover, {
          workspaceId: "",
          runId: "",
          path: "desktop/src/appearance.css",
          additions: 10,
          deletions: 0,
          previewLines,
          style: { position: "static" },
        }),
        h(EditedFilesCard, {
          files,
          workspacePath: "",
          onOpenFile: (path: string) => { last.value = `open-file: ${path}`; },
          onUndo: () => { last.value = "undo"; },
          onReview: () => { last.value = "review"; },
        }),
      ]);
    return () => h("div", { class: "wrap" }, [stage("light"), stage("dark"), h("p", { class: "log" }, last.value || "\u00a0")]);
  },
};

createApp(Demo).use(i18n).mount("#app");
