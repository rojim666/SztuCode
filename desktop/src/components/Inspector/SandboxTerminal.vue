<script setup lang="ts">
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import { onBeforeUnmount, onMounted, ref } from "vue";
import "@xterm/xterm/css/xterm.css";
import {
  sandboxPtyClose,
  sandboxPtyResize,
  sandboxPtyStart,
  sandboxPtyWrite,
} from "../../services/sztu-runtime";

const props = defineProps<{ workspacePath: string }>();
type PtyOutput = { session_id: string; data: number[] };

const terminalRoot = ref<HTMLElement | null>(null);
const sessionId = crypto.randomUUID();
const decoder = new TextDecoder();
let terminal: Terminal | null = null;
let fitAddon: FitAddon | null = null;
let resizeObserver: ResizeObserver | null = null;
let unlistenOutput: UnlistenFn | null = null;
let inputDisposable: { dispose(): void } | null = null;
let resizeDisposable: { dispose(): void } | null = null;
let writeQueue = Promise.resolve();
const pendingInput: string[] = [];
let started = false;
let disposed = false;
let themeObserver: MutationObserver | null = null;

function terminalTheme() {
  const dark = document.documentElement.dataset.appTheme === "dark";
  return {
    background: "rgba(0, 0, 0, 0)",
    foreground: dark ? "#e7eeee" : "#273238",
    cursor: dark ? "#b7d7c8" : "#315c4d",
    cursorAccent: dark ? "#202425" : "#ffffff",
    selectionBackground: dark ? "#47705f99" : "#98c4ad99",
    black: dark ? "#17201d" : "#273238",
    red: dark ? "#f18b84" : "#a63e36",
    green: dark ? "#8bd5ad" : "#18794e",
    yellow: dark ? "#e5c27a" : "#8a6116",
    blue: dark ? "#8ebeff" : "#175cd3",
    magenta: dark ? "#d5a4e7" : "#8e3ba8",
    cyan: dark ? "#82d4d5" : "#087e8b",
    white: dark ? "#dbe5e3" : "#f5f5f5",
    brightBlack: dark ? "#82908c" : "#666666",
    brightRed: dark ? "#ffaaa3" : "#d92d20",
    brightGreen: dark ? "#a5e8c1" : "#16803d",
    brightYellow: dark ? "#f2d694" : "#a66f00",
    brightBlue: dark ? "#b0d0ff" : "#1570ef",
    brightMagenta: dark ? "#e5baf4" : "#a445b8",
    brightCyan: dark ? "#a4e9e7" : "#0891a6",
    brightWhite: dark ? "#ffffff" : "#ffffff",
  };
}

function showError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  terminal?.writeln(`\r\n${message}`);
}

function sendInput(data: string) {
  if (!started) {
    pendingInput.push(data);
    return;
  }
  writeQueue = writeQueue.then(() => sandboxPtyWrite(sessionId, data)).catch(showError);
}

async function initialize() {
  if (!terminalRoot.value) return;
  terminal = new Terminal({
    allowTransparency: true,
    cursorBlink: true,
    cursorStyle: "block",
    convertEol: true,
    fontFamily: "Consolas, monospace",
    fontSize: 14,
    lineHeight: 1.08,
    letterSpacing: 0,
    scrollback: 3000,
    theme: terminalTheme(),
  });
  fitAddon = new FitAddon();
  terminal.loadAddon(fitAddon);
  terminal.open(terminalRoot.value);
  themeObserver = new MutationObserver(() => {
    if (terminal) terminal.options.theme = terminalTheme();
  });
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-app-theme"] });
  terminal.writeln("Windows PowerShell");
  terminal.writeln("Copyright (C) Microsoft Corporation. All rights reserved.");
  terminal.writeln("");

  try {
    unlistenOutput = await listen<PtyOutput>("sandbox:pty-output", ({ payload }) => {
      if (payload.session_id !== sessionId || disposed) return;
      terminal?.write(decoder.decode(Uint8Array.from(payload.data), { stream: true }));
    });
    inputDisposable = terminal.onData(sendInput);
    fitAddon.fit();
    await sandboxPtyStart(sessionId, props.workspacePath, terminal.cols, terminal.rows);
    if (disposed) {
      await sandboxPtyClose(sessionId);
      return;
    }
    started = true;
    for (const data of pendingInput.splice(0)) sendInput(data);
    resizeDisposable = terminal.onResize(({ cols, rows }) => {
      void sandboxPtyResize(sessionId, cols, rows).catch(showError);
    });
    terminal.focus();
  } catch (error) {
    showError(error);
  }
}

onMounted(() => {
  if (!terminalRoot.value) return;
  terminalRoot.value.addEventListener("pointerdown", () => terminal?.focus());
  resizeObserver = new ResizeObserver(() => {
    requestAnimationFrame(() => {
      if (terminalRoot.value?.clientWidth && terminalRoot.value.clientHeight) fitAddon?.fit();
    });
  });
  resizeObserver.observe(terminalRoot.value);
  void initialize();
});

onBeforeUnmount(() => {
  disposed = true;
  resizeObserver?.disconnect();
  themeObserver?.disconnect();
  inputDisposable?.dispose();
  resizeDisposable?.dispose();
  unlistenOutput?.();
  if (started) void sandboxPtyClose(sessionId);
  terminal?.dispose();
  resizeObserver = null;
  themeObserver = null;
  inputDisposable = null;
  resizeDisposable = null;
  unlistenOutput = null;
  fitAddon = null;
  terminal = null;
});
</script>

<template>
  <div ref="terminalRoot" class="xterm-shell" aria-label="PowerShell 终端" />
</template>
