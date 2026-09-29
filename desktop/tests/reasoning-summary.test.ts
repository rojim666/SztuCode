import assert from "node:assert/strict";
import test from "node:test";
import { firstLine, latestLine, reasoningSummary, showLiveThinkingRow } from "../src/utils/reasoningSummary";

test("firstLine returns the whole text when there is no newline", () => {
  assert.equal(firstLine("单行思考"), "单行思考");
});

test("firstLine cuts at the first newline", () => {
  assert.equal(firstLine("第一行\n第二行\n第三行"), "第一行");
});

test("latestLine ignores trailing whitespace before the last newline", () => {
  assert.equal(latestLine("第一行\n第二行\n"), "第二行");
});

test("latestLine returns the last line", () => {
  assert.equal(latestLine("a\nb\nc"), "c");
});

test("reasoningSummary picks the latest line while running and the first line when settled", () => {
  const text = "第一行\n第二行";
  assert.equal(reasoningSummary(text, true), "第二行");
  assert.equal(reasoningSummary(text, false), "第一行");
});

test("reasoningSummary returns an empty summary for blank text", () => {
  assert.equal(reasoningSummary(" \n ", true), "");
});

// 真实 DeepSeek 流式思考分片（runtime-ts-events.jsonl，run 04287933，model deepseek-flash）：
// 逐分片回放，任何一帧都不能让折叠行的实时预览消失（回归提交 2c31ef3 的自遮蔽）
const DEEPSEEK_THINKING_CHUNKS = [
  "Now", " I", " have", " the", " full", " picture",
  " of", " the", " current", " behavior", ".", " Let",
  " me", " reconstruct", ":\n\n", "**", "Current", " main",
  "-t", "im", "eline", " thinking", " display", " (",
  "Activity", "Phase", "):", "**\n", "1", ".",
];

test("collapsed row keeps the live thinking preview on every streaming chunk", () => {
  let thinking = "";
  for (const chunk of DEEPSEEK_THINKING_CHUNKS) {
    thinking += chunk;
    assert.equal(
      showLiveThinkingRow({ running: true, thinking }),
      true,
      `live preview hid itself after chunk ${JSON.stringify(chunk)}`,
    );
  }
});

test("a plan title hands the row back to the purpose label", () => {
  assert.equal(showLiveThinkingRow({ planTitle: "修复登录", running: true, thinking: "Now I have the full picture" }), false);
  // 空白标题不算 plan 语义，预览照常显示
  assert.equal(showLiveThinkingRow({ planTitle: "   ", running: true, thinking: "Now" }), true);
});

test("settled or thinking-less rows show no live preview", () => {
  assert.equal(showLiveThinkingRow({ running: false, thinking: "Now" }), false);
  assert.equal(showLiveThinkingRow({ running: true, thinking: "" }), false);
  assert.equal(showLiveThinkingRow({ running: true, thinking: "  \n " }), false);
});
