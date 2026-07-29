import { Command } from "lucide-react";
import { useEffect, useRef } from "react";
import type { PaletteCommand } from "../../types";

type CommandPaletteProps = {
  open: boolean;
  query: string;
  commands: PaletteCommand[];
  onQueryChange: (value: string) => void;
  onClose: () => void;
};

/** 命令面板（Ctrl+K）：搜索并执行快捷操作 */
export function CommandPalette({
  open,
  query,
  commands,
  onQueryChange,
  onClose,
}: CommandPaletteProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  if (!open) return null;

  const matching = commands.filter((cmd) =>
    `${cmd.title} ${cmd.detail}`.toLowerCase().includes(query.toLowerCase()),
  );

  function run(command: PaletteCommand) {
    if (command.disabled) return;
    command.action();
    onClose();
  }

  return (
    <section
      className="command-palette"
      role="dialog"
      aria-modal="true"
      aria-label="命令面板"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="palette-sheet">
        <header>
          <Command size={17} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && matching[0]) run(matching[0]);
            }}
            placeholder="搜索命令、工作区或任务操作…"
          />
          <kbd>Esc</kbd>
        </header>
        <div className="palette-list">
          {matching.map((command) => (
            <button
              key={command.id}
              disabled={command.disabled}
              onClick={() => run(command)}
            >
              <div>
                <b>{command.title}</b>
                <span>{command.detail}</span>
              </div>
              {command.key && <kbd>{command.key}</kbd>}
            </button>
          ))}
          {!matching.length && <p>没有匹配的命令。</p>}
        </div>
      </div>
    </section>
  );
}
