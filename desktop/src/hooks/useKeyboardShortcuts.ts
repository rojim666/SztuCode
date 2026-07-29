import { useEffect } from "react";

type ShortcutHandler = (event: KeyboardEvent) => void;

/** 键盘快捷键绑定 */
export function useKeyboardShortcuts(handlers: Record<string, ShortcutHandler>) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const ctrl = event.ctrlKey || event.metaKey;
      const shift = event.shiftKey;
      const key = event.key.toLowerCase();

      // Ctrl+K — 命令面板
      if (ctrl && key === "k") {
        event.preventDefault();
        handlers.onCommandPalette?.(event);
      }
      // Ctrl+N — 新建任务
      if (ctrl && key === "n") {
        event.preventDefault();
        handlers.onNewTask?.(event);
      }
      // Ctrl+Shift+P — 计划模式
      if (ctrl && shift && key === "p") {
        event.preventDefault();
        handlers.onPlanMode?.(event);
      }
      // Ctrl+2 — 聚焦输入
      if (ctrl && event.key === "2") {
        event.preventDefault();
        handlers.onFocusComposer?.(event);
      }
      // Escape — 关闭面板
      if (event.key === "Escape") {
        handlers.onEscape?.(event);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handlers]);
}
