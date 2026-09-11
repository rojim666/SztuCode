import assert from "node:assert/strict";
import test from "node:test";
import { canAddImageAttachments, imageProcessingMode } from "../src/utils/modelVision.js";

test("image processing mode is explicit for vision and text-only profiles", () => {
  assert.equal(imageProcessingMode("qwen2.5-vl", true), "direct");
  assert.equal(imageProcessingMode("deepseek-chat", false), "ocr");
});

test("desktop enforces the daemon image-count limit", () => {
  assert.equal(canAddImageAttachments(19, 1), true);
  assert.equal(canAddImageAttachments(20, 1), false);
});
