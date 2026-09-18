import type { DragDropEvent } from "@tauri-apps/api/webview";

export function createComposerFileDropHandler(options: {
  pixelRatio: () => number;
  containsPoint: (x: number, y: number) => boolean;
  setHover: (hover: boolean) => void;
  addPaths: (paths: string[]) => Promise<void>;
  onError: (error: unknown) => void;
}) {
  return async (event: { payload: DragDropEvent }): Promise<void> => {
    const payload = event.payload;
    if (payload.type === "leave") {
      options.setHover(false);
      return;
    }
    // Tauri reports physical pixels; DOM hit testing uses CSS pixels.
    const ratio = options.pixelRatio();
    const inside = options.containsPoint(payload.position.x / ratio, payload.position.y / ratio);
    options.setHover(payload.type !== "drop" && inside);
    if (payload.type === "drop" && inside && payload.paths.length) {
      try {
        await options.addPaths(payload.paths);
      } catch (error) {
        options.onError(error);
      }
    }
  };
}
