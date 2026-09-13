import { isTauri, invoke } from "@tauri-apps/api/core";
import { relaunch } from "@tauri-apps/plugin-process";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { reactive, readonly } from "vue";

type Phase = "idle" | "checking" | "available" | "latest" | "downloading" | "installing" | "installed" | "restarting";
// Keep the operation alive when the settings dialog is closed and reopened.
const state = reactive({ phase: "idle" as Phase, version: "", notes: "", downloaded: 0, total: 0, error: "", message: "" });
let update: Update | null = null;
const busy = () => ["checking", "downloading", "installing", "restarting"].includes(state.phase);

export const appUpdateState = readonly(state);

export async function checkAppUpdate() {
  if (busy() || state.phase === "installed") return;
  state.error = "";
  state.message = "";
  if (!isTauri()) {
    state.message = "desktopOnly";
    return;
  }
  state.phase = "checking";
  try {
    if (!await invoke<boolean>("updater_configured")) {
      state.message = "notConfigured";
      state.phase = "idle";
      return;
    }
    if (update) {
      await update.close();
      update = null;
    }
    state.version = "";
    state.notes = "";
    update = await check({ timeout: 20_000 });
    state.version = update?.version ?? "";
    state.notes = update?.body ?? "";
    state.phase = update ? "available" : "latest";
  } catch (error) {
    state.phase = "idle";
    state.error = String(error);
  }
}

export async function installAppUpdate() {
  if (!update || state.phase !== "available") return;
  state.phase = "downloading";
  state.error = "";
  state.downloaded = 0;
  state.total = 0;
  try {
    await update.download((event) => {
      if (event.event === "Started") {
        state.downloaded = 0;
        state.total = event.data.contentLength ?? 0;
      } else if (event.event === "Progress") {
        state.downloaded += event.data.chunkLength;
      }
    }, { timeout: 120_000 });
    state.phase = "installing";
    await update.install();
    state.phase = "installed";
    // Windows exits through its installer; other platforms offer an explicit restart.
    await update.close().catch(() => undefined);
    update = null;
  } catch (error) {
    state.phase = "available";
    state.error = String(error);
  }
}

export async function restartAfterUpdate() {
  if (state.phase !== "installed") return;
  state.phase = "restarting";
  state.error = "";
  try {
    await relaunch();
  } catch (error) {
    state.phase = "installed";
    state.error = String(error);
  }
}
