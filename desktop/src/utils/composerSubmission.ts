export type ComposerSubmitMode = "queue" | "steer";
export type ComposerSubmitGesture = "enter" | "accelerated";

export type QueueDockItem = {
  id: string;
  text: string;
  attachmentCount: number;
};

export function resolveComposerSubmitMode(
  running: boolean,
  gesture: ComposerSubmitGesture,
  steeringAvailable: boolean,
  preferredWhenBusy: ComposerSubmitMode = "queue",
): ComposerSubmitMode {
  if (!running || !steeringAvailable) return "queue";
  if (gesture === "enter") return preferredWhenBusy;
  return preferredWhenBusy === "queue" ? "steer" : "queue";
}
