import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";
import type { TimelineItem as TimelineItemType } from "../../types";
import { EmptyState } from "./EmptyState";
import { TimelineEntry } from "./TimelineItem";

type TimelineProps = {
  items: TimelineItemType[];
  onSuggestion: (prompt: string) => void;
};

/** 时间线区域：虚拟滚动 + 空状态 */
export function Timeline({ items, onSuggestion }: TimelineProps) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 108,
    overscan: 10,
  });

  return (
    <div className="timeline" ref={parentRef}>
      {!items.length && <EmptyState onSuggestion={onSuggestion} />}

      {items.length > 0 && (
        <div
          className="timeline-virtual"
          style={{ height: virtualizer.getTotalSize() }}
        >
          {virtualizer.getVirtualItems().map((virtualItem) => {
            const item = items[virtualItem.index];
            return (
              <TimelineEntry
                key={item.id}
                item={item}
                measureRef={virtualizer.measureElement}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
